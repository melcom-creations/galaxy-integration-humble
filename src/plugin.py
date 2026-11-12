import warnings
# Suppress Python warnings so they do not pollute GOG Galaxy output.
warnings.filterwarnings("ignore")

import sys
import asyncio
import logging
import re
import webbrowser
import pathlib
import json
import calendar
import typing as t
import time
from functools import partial

def _add_modules_to_sys_path() -> None:
    base_dir = pathlib.Path(__file__).resolve().parent
    candidate_dirs = [base_dir / 'modules', base_dir / 'Modules']

    try:
        candidate_dirs.extend(
            d for d in base_dir.iterdir()
            if d.is_dir() and d.name.lower() == 'modules'
        )
    except OSError:
        # Keep startup resilient even if listing the plugin directory fails.
        pass

    for candidate_dir in candidate_dirs:
        candidate_path = str(candidate_dir.resolve())
        if candidate_dir.is_dir() and candidate_path not in sys.path:
            sys.path.insert(0, candidate_path)
            return

_add_modules_to_sys_path()

from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.consts import Platform, OSCompatibility, LocalGameState
from galaxy.api.types import Authentication, NextStep, LocalGame, Game, GameLibrarySettings, Subscription, SubscriptionGame, GameTime
from galaxy.api.errors import AuthenticationRequired, UnknownError, ImportInProgress

from consts import IS_WINDOWS, TROVE_SUBSCRIPTION_NAME
from settings import Settings
from webservice import AuthorizedHumbleAPI
from webservice import LocalBrowserAuthServer
from webservice import galaxy_confirmation_visible
from model.game import TroveGame, Key, Subproduct, HumbleGame, ChoiceGame
from model.types import HP
from library import LibraryResolver
from local import AppFinder
from local.localgame import LocalHumbleGame
from local.humbleapp_adapter import HumbleAppGameCategory, HumbleAppClient
from privacy import SensitiveFilter
from utils.decorators import double_click_effect

with open(pathlib.Path(__file__).parent / 'manifest.json') as f:
    __version__ = json.load(f)['version']

logger = logging.getLogger()
logger.addFilter(SensitiveFilter())

def setup_sentry():
    # Keep Sentry disabled so it does not write to stdout.
    pass

class HumbleBundlePlugin(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(Platform.HumbleBundle, __version__, reader, writer, token)
        headers = {"User-Agent": f"HumbleBundle plugin for GOG Galaxy 2.0 v{__version__}"}
        self._api = AuthorizedHumbleAPI(headers=headers, credentials_callback=self.store_credentials)
        self._browser_auth = LocalBrowserAuthServer()
        self._app_finder = AppFinder()
        self._settings = Settings()
        self._configurator_opened = False
        self._closing = False
        self._library_resolver = None
        self._humbleapp_client = HumbleAppClient()

        self._owned_games: t.Dict[str, HumbleGame] = {}
        self._trove_games: t.Dict[str, TroveGame] = {}  # Keep Trove games in memory while restoring cached entries.
        self._choice_games: t.Dict[str, ChoiceGame] = {}

        self._local_games: t.Dict[str, LocalHumbleGame] = {}
        self._cached_game_states = {}

        self._getting_owned_games = asyncio.Lock()
        self._owned_check: asyncio.Task = asyncio.create_task(asyncio.sleep(8))
        self._statuses_check: asyncio.Task = asyncio.create_task(asyncio.sleep(4))
        self._installed_check: asyncio.Task = asyncio.create_task(asyncio.sleep(4))
        self._humbleapp_config_check: asyncio.Task = asyncio.create_task(asyncio.sleep(0))

        self._rescan_needed = True
        self._next_folder_scan = 0.0
        self._under_installation = set()
        
        # Track active game sessions and their launch timestamps.
        self._active_sessions: t.Dict[str, float] = {}

    @property
    def _humble_games(self) -> t.Dict[str, HumbleGame]:
        """
        Alias for cached owned and subscription games mapped by id.
        In case of id duplication, owned games got priority.
        """
        return {
            **self._choice_games,
            **self._trove_games,
            **self._owned_games
        }

    def _save_cache(self, key: str, data: t.Any):
        data = json.dumps(data)
        self.persistent_cache[key] = data
        self.push_cache()

    def _load_cache(self, key: str, default: t.Any=None) -> t.Any:
        if key in self.persistent_cache:
            return json.loads(self.persistent_cache[key])
        return default

    def _maybe_open_install_config(self, force: bool = False):
        """Prompt once per plugin run until a game-folder configuration is available."""
        config_exists = self._settings.LOCAL_CONFIG_FILE.is_file()
        if not force:
            if config_exists and self._settings.installed.search_dirs:
                return
            if self._configurator_opened:
                return

        try:
            # Only write the default configuration if the file does not exist yet.
            # Preserve settings generated by the interactive batch configurator.
            if not config_exists:
                self._settings.save_config()
                
            self._settings.open_config_file()
            self._configurator_opened = True
        except Exception as e:
            logging.exception(e)

    def handshake_complete(self):
        self._library_resolver = LibraryResolver(
            api=self._api,
            settings=self._settings.library,
            cache=self._load_cache('library', {}),
            save_cache_callback=partial(self._save_cache, 'library')
        )
        self._last_version = self._load_cache('last_version', default=None)
        self._trove_games = {g['machine_name']: TroveGame(g) for g in self._load_cache('trove_games', [])}
        self._choice_games = {g['id']: ChoiceGame(**g) for g in self._load_cache('choice_games', [])}
        # Remove cache entries that are no longer used.
        self.persistent_cache.pop('next_fetch_orders', None)
    
    async def _get_user_name(self) -> str:
        identity = self._api.modern.identity or {}
        public = identity.get('metadata_public') or {}
        if not isinstance(public, dict):
            return 'Humble User'
        return public.get('gog_username') or 'Humble User'

    
    async def _do_auth(self, auth_cookie) -> Authentication:
        user_id = await self._api.authenticate(auth_cookie)
        user_name = await self._get_user_name() or "Humble User"
        return Authentication(user_id, user_name)

    async def _login_step(self):
        # Galaxy may request authentication while its connection prompt is open.
        while galaxy_confirmation_visible():
            if self._closing:
                raise AuthenticationRequired()
            await asyncio.sleep(0.1)
        # Allow Galaxy's cancel request to arrive before returning an auth window.
        await asyncio.sleep(0.1)
        if self._closing:
            raise AuthenticationRequired()
        await self._browser_auth.start()
        return NextStep("web_session", {
            "window_title": "Login to HumbleBundle",
            "window_width": 520,
            "window_height": 260,
            "start_uri": self._browser_auth.base_url,
            "end_uri_regex": self._browser_auth.end_uri_regex,
        })

    async def authenticate(self, stored_credentials=None):
        self._save_cache('last_version', __version__)

        if not stored_credentials:
            return await self._login_step()

        logging.info('Stored credentials found')
        try:
            auth: Authentication = await self._do_auth(stored_credentials)
        except AuthenticationRequired:
            logger.info("Stored Humble session was rejected; requesting interactive sign-in")
            return await self._login_step()
        self._maybe_open_install_config()
        return auth

    async def pass_login_credentials(self, step, credentials, cookies):
        result = self._browser_auth.result
        if result is None:
            raise AuthenticationRequired()
        try:
            auth = await self._do_auth({'type': 'ory', 'cookies': result.cookies})
        finally:
            await self._browser_auth.stop()
        self._maybe_open_install_config()
        return auth

    async def get_owned_games(self):
        if not self._api.is_authenticated:
            raise AuthenticationRequired()

        async with self._getting_owned_games:
            logging.debug('getting owned games')
            library_resolver = self._library_resolver
            if library_resolver is None:
                raise UnknownError()
            self._owned_games = await library_resolver()
            games = [g.in_galaxy_format() for g in self._owned_games.values()]
            return [game for game in games if isinstance(game, Game)]

    @staticmethod
    def _normalize_subscription_name(machine_name: str):
        month_map = {
            'january': '01',
            'february': '02',
            'march': '03',
            'april': '04',
            'may': '05',
            'june': '06',
            'july': '07',
            'august': '08',
            'september': '09',
            'october': '10',
            'november': '11',
            'december': '12'
        }
        try:
            month, year, type_ = machine_name.split('_')
            month_number = month_map[month.lower()]
        except Exception:
            logging.warning(f'Unexpected Humble subscription machine name: {machine_name!r}')
            return machine_name.replace('_', ' ').title()
        return f'Humble {type_.title()} {year}-{month_number}'

    @staticmethod
    def _choice_name_to_slug(subscription_name: str):
        _, _, year_month = subscription_name.split(' ')
        year, month = year_month.split('-')
        return f'{calendar.month_name[int(month)]}-{year}'.lower()

    async def get_subscriptions(self):
        await self._api.modern.refresh_library()
        active = self._api.modern.state.get('hasActiveSubscription') is True
        result = [Subscription(category.value, owned=active) for category in HumbleAppGameCategory]
        months = set()
        for row in self._api.modern.items:
            value = row.get('choiceDate')
            if isinstance(value, str) and re.match(r'^\d{4}-\d{2}', value):
                months.add('Humble Choice ' + value[:7])
        self._modern_choice_months = months
        cached = {'Humble Choice ' + game.slug[-4:] + '-' + str(list(calendar.month_name).index(game.slug[:-5].title())).zfill(2)
                  for game in self._choice_games.values()
                  if re.match(r'^[a-z]+-\d{4}$', game.slug) and game.slug[:-5].title() in calendar.month_name}
        result.extend(Subscription(month, owned=month in months) for month in sorted(months | cached, reverse=True))
        return result


    async def get_subscription_games(self, subscription_name: str, context: None) -> t.AsyncGenerator[t.List[SubscriptionGame], None]:  # type: ignore
        if subscription_name in [n.value for n in HumbleAppGameCategory]:
            yield self._humbleapp_client.get_subscription_games(HumbleAppGameCategory(subscription_name))
            return

        if subscription_name == TROVE_SUBSCRIPTION_NAME:
            raise UnknownError("Plugin does not support Trove games any longer")

        await self._api.modern.refresh_library()
        year_month = subscription_name.removeprefix('Humble Choice ')
        slug = self._choice_name_to_slug(subscription_name)
        matches = {game.id: game for game in self._choice_games.values() if game.slug == slug}
        known_titles = {game.title.casefold(): game.id for game in matches.values()}
        for row in self._api.modern.items:
            if not str(row.get('choiceDate', '')).startswith(year_month):
                continue
            identifier = row.get('contentId')
            if not isinstance(identifier, str) or not identifier or identifier.startswith('$'):
                continue
            title = row.get('title')
            if not isinstance(title, str) or not title:
                continue
            identifier = known_titles.get(title.casefold(), identifier)
            matches[identifier] = ChoiceGame(identifier, title, slug)
        self._choice_games.update(matches)
        yield [game.in_galaxy_format() for game in matches.values()]
        return


    def subscription_games_import_complete(self):
        self._save_cache('choice_games', [game.serialize() for game in self._choice_games.values()])

    async def get_local_games(self) -> t.List[LocalGame]:
        self._rescan_needed = True
        self._humbleapp_client.refresh_game_list()
        humble_app_games = self._humbleapp_client.get_local_games()
        other_detected_installed_games = [g.in_galaxy_format() for g in self._local_games.values()]
        return humble_app_games + other_detected_installed_games

    @double_click_effect(0.35, '_maybe_open_install_config', True)
    async def install_game(self, game_id):
        if game_id in self._under_installation:
            return

        self._under_installation.add(game_id)
        game = None
        try:
            if game_id in self._humbleapp_client:
                self._humbleapp_client.install(game_id)
                return

            game = self._humble_games.get(game_id)
            if game is None:
                logging.error(f'Install game: game {game_id} not found. Humble games: {self._humble_games.keys()}')
                return

            if isinstance(game, ChoiceGame):
                webbrowser.open(self._api.modern.presentation_url(game_id, game.human_name))
                return

            if isinstance(game, Key):
                webbrowser.open(game._data.get('library_url') or self._api.modern.presentation_url(game_id, game.human_name))
                return

            if isinstance(game, Subproduct):
                webbrowser.open(game._data.get('library_url') or self._api.modern.presentation_url(game_id, game.human_name))
                return

        except Exception as e:
            logging.error(e, extra={'game': game} if game is not None else None)
            raise
        finally:
            self._under_installation.remove(game_id)

    async def get_game_library_settings(self, game_id: str, context: t.Any) -> GameLibrarySettings:
        gls = GameLibrarySettings(game_id, None, None)
        if game_id in self._humbleapp_client:
            return gls
        game = self._humble_games[game_id]
        if isinstance(game, Key):
            gls.tags = ['Key']
            if game.key_val is None:
                gls.tags.append('Unrevealed')
        if isinstance(game, TroveGame):
            gls.tags = []  # Clear redundant tags because Galaxy already supports subscriptions.
        return gls

    async def launch_game(self, game_id):
        if game_id in self._humbleapp_client:
            self._humbleapp_client.launch(game_id)
        else:
            try:
                game = self._local_games[game_id]
            except KeyError as e:
                logging.error(e, extra={'local_games': self._local_games})
            else:
                game.run()

    async def uninstall_game(self, game_id):
        if game_id in self._humbleapp_client:
            self._humbleapp_client.uninstall(game_id)
        else:
            try:
                game = self._local_games[game_id]
            except KeyError as e:
                logging.error(e, extra={'local_games': self._local_games})
            else:
                game.uninstall()

    async def get_local_size(self, game_id, context) -> t.Optional[int]:
        if game_id in self._humbleapp_client:
            return self._humbleapp_client.get_local_size(game_id)
        else:
            try:
                game = self._local_games[game_id]
            except KeyError as e:
                logging.error(e, extra={'local_games': self._local_games})
                return None
            return await game.get_size()

    async def get_os_compatibility(self, game_id: str, context: t.Any) -> t.Optional[OSCompatibility]:
        if game_id in self._humbleapp_client:
            return self._humbleapp_client.os_compatibility
        
        try:
            game = self._humble_games[game_id]
        except KeyError as e:
            logging.error(e, extra={'humble_games': self._humble_games})
            return None

        # Treat keys as OS-independent so the Install button remains available.
        if isinstance(game, Key):
            return OSCompatibility(0b111)

        HP_OS_MAP = {
            HP.WINDOWS: OSCompatibility.Windows,
            HP.MAC: OSCompatibility.MacOS,
            HP.LINUX: OSCompatibility.Linux
        }
        osc = OSCompatibility(0)
        for humble_platform in game.downloads:
            osc |= HP_OS_MAP.get(humble_platform, OSCompatibility(0))
        return osc if osc else None

    async def _check_owned(self):
        async with self._getting_owned_games:
            library_resolver = self._library_resolver
            if library_resolver is None:
                return
            old_ids = self._owned_games.keys()
            self._owned_games = await library_resolver(only_cache=True)
            for old_id in old_ids - self._owned_games.keys():
                self.remove_game(old_id)
            for new_id in self._owned_games.keys() - old_ids:
                game = self._owned_games[new_id].in_galaxy_format()
                if isinstance(game, Game):
                    self.add_game(game)
        # Increase the throttle to reduce the impact of rapid library updates.
        await asyncio.sleep(3)

    async def _check_installed(self):
        """
        Owned games are needed to local games search. Galaxy methods call order is:
        get_local_games -> authenticate -> get_local_games -> get_owned_games (at the end!).
        That is why the plugin sets all logic of getting local games in perdiodic checks like this one.
        """
        if not self._owned_games:
            logging.debug('Skipping perdiodic check for local games as owned games not found yet.')
            return

        hp = HP.WINDOWS if IS_WINDOWS else HP.MAC
        installable_title_id = {
            game.human_name: uid for uid, game
            in {**self._owned_games, **self._trove_games}.items()
            if game.os_compatibile(hp)
        }
        try:
            scan_folders = self._rescan_needed or time.monotonic() >= self._next_folder_scan
            if scan_folders:
                self._rescan_needed = False
                logging.debug(f'Checking installed games with path scanning in: {self._settings.installed.search_dirs}')
                found_games = await self._app_finder(installable_title_id, self._settings.installed.search_dirs)
                self._next_folder_scan = time.monotonic() + 8
            else:
                found_games = await self._app_finder(installable_title_id, None)
            for game_id, game in found_games.items():
                previous = self._local_games.get(game_id)
                if previous is not None and previous.executable == game.executable:
                    # A rescan must retain the process used for running state and playtime.
                    game.process = previous.process
            # Registry scans return new entries, so keep previously detected games.
            self._local_games.update(found_games)
        except Exception:
            self._rescan_needed = True
            raise
        await asyncio.sleep(4)

    async def _check_statuses(self):
        """Checks satuses of local games. Detects changes in local games when the game is:
        - installed (local games list appended in _check_installed)
        - uninstalled (exe no longer exists)
        - launched (via Galaxy - pid tracking started)
        - stopped (process no longer running/is zombie)
        """
        freezed_locals = list(self._local_games.values())
        for game in freezed_locals:
            state = game.state
            old_state = self._cached_game_states.get(game.id)
            if state == old_state:
                continue
                
            # Track running states to calculate real-time playtime sessions.
            was_running = bool(old_state & LocalGameState.Running) if old_state is not None else False
            is_running = bool(state & LocalGameState.Running) if state is not None else False
            
            if not was_running and is_running:
                # Capture the session start timestamp when a game is launched.
                self._active_sessions[game.id] = time.time()
                logger.info(f"Playtime tracking: Session started for game {game.id}")
            elif was_running and not is_running:
                # Calculate elapsed minutes once the game stops running.
                start_time = self._active_sessions.pop(game.id, None)
                if start_time:
                    # Round the elapsed time to the nearest minute to avoid truncation loss.
                    duration_mins = round((time.time() - start_time) / 60)
                    if duration_mins > 0:
                        time_key = f"time_{game.id}"
                        last_key = f"last_{game.id}"
                        
                        current_total = int(self._load_cache(time_key, 0))
                        new_total = current_total + duration_mins
                        end_time_stamp = int(time.time())
                        
                        self._save_cache(time_key, new_total)
                        self._save_cache(last_key, end_time_stamp)
                        
                        # Publish the updated session statistics to GOG Galaxy immediately.
                        self.update_game_time(GameTime(game.id, new_total, end_time_stamp))
                        logger.info(f"Playtime tracking: Session ended for game {game.id}. Added {duration_mins} mins. Total: {new_total} mins.")

            self.update_local_game_status(LocalGame(game.id, state))
            self._cached_game_states[game.id] = state
        await asyncio.sleep(0.5)
    
    async def _check_humbleapp(self):
        self._humbleapp_client.refresh_game_list()
        await asyncio.sleep(1)

    def tick(self):
        self._settings.reload_config_if_changed()

        if self._owned_check.done() and self._settings.library.has_changed():
            self._owned_check = asyncio.create_task(self._check_owned())

        if self._settings.installed.has_changed():
            self._rescan_needed = True

        if self._installed_check.done():
            self._installed_check = asyncio.create_task(self._check_installed())

        if self._statuses_check.done():
            self._statuses_check = asyncio.create_task(self._check_statuses())
        
        if self._humbleapp_config_check.done():
            self._humbleapp_config_check = asyncio.create_task(self._check_humbleapp())

    async def get_game_time(self, game_id: str, context: t.Any) -> GameTime:
        """
        Retrieves the persistent total playtime and last played date from GOG's cache.
        """
        time_key = f"time_{game_id}"
        last_key = f"last_{game_id}"
        
        time_played = self._load_cache(time_key, None)
        last_played = self._load_cache(last_key, None)
        
        return GameTime(
            game_id=game_id,
            time_played=time_played,
            last_played_time=last_played
        )

    async def _start_game_times_import(self, game_ids: t.List[str]) -> None:
        try:
            await super()._start_game_times_import(game_ids)
        except ImportInProgress:
            logger.debug("Game time import request ignored while an import is already running")

    async def shutdown(self):
        self._closing = True
        self._owned_check.cancel()
        self._statuses_check.cancel()
        self._installed_check.cancel()
        self._humbleapp_config_check.cancel()
        await self._browser_auth.stop()
        await self._api.close_session()

def main():
    # Keep Sentry disabled so it does not write to stdout.
    create_and_run_plugin(HumbleBundlePlugin, sys.argv)

if __name__ == "__main__":
    main()
