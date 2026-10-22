from http.cookies import SimpleCookie
from http import HTTPStatus
from contextlib import contextmanager
import typing as t
import aiohttp
import json
import base64
import logging

import yarl
import galaxy.http
from galaxy.api.errors import UnknownBackendResponse, AuthenticationRequired

from model.download import  DownloadStructItem
from model.subscription import MontlyContentData, ChoiceContentData, ChoiceMonth


logger = logging.getLogger(__name__)


@contextmanager
def handle_exception():
    """Wrapper over galaxy.http to log error details"""
    with galaxy.http.handle_exception():
        try:
            yield
        except Exception as e:
            logger.error("Humble request failed (%s)", type(e).__name__)
            raise


class WebpackParseError(UnknownBackendResponse):
    pass


class AuthorizedHumbleAPI:
    _AUTHORITY = "https://www.humblebundle.com/"
    _AUTH_COOKIE_NAME = "_simpleauth_sess"
    _PROCESS_LOGIN = "processlogin"
    _ORDER_LIST_URL = "api/v1/user/order"
    _ORDER_URL = "/api/v1/order/{}"
    _ORDERS_BULK_URL = "api/v1/orders"

    TROVES_PER_CHUNK = 20
    _MAIN_PAGE = ""
    _SUBSCRIPTION = 'membership'
    _SUBSCRIPTION_HOME = 'membership/home'
    _SUBSCRIPTION_PRODUCTS = 'api/v1/subscriptions/humble_monthly/subscription_products_with_gamekeys'
    _SUBSCRIPTION_HISTORY = 'api/v1/subscriptions/humble_monthly/history?from_product={}'
    _DOWNLOAD_SIGN = 'api/v1/user/download/sign'
    _HUMBLER_REDEEM_DOWNLOAD = 'humbler/redeemdownload'

    _DEFAULT_HEADERS = {
        "Accept": "application/json",
        "Accept-Charset": "utf-8",
        "Keep-Alive": "true",
    }

    def __init__(self, headers: t.Dict[str, t.Any],
                 credentials_callback: t.Optional[t.Callable[[dict], None]] = None):
        headers={**self._DEFAULT_HEADERS, **headers}
        self._session = galaxy.http.create_client_session(headers=headers)
        self._credentials_callback = credentials_callback
        self._authenticated = False
        self._user_id: t.Optional[str] = None
        self._session_cookie: t.Optional[str] = None
        self._last_stored_cookie: t.Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated and self._session_cookie is not None

    def _set_session_cookie(self, value: str) -> None:
        cookie = SimpleCookie()
        cookie[self._AUTH_COOKIE_NAME] = value
        cookie[self._AUTH_COOKIE_NAME]['path'] = '/'
        self._session.cookie_jar.clear(lambda item: item.key == self._AUTH_COOKIE_NAME)
        self._session.cookie_jar.update_cookies(cookie, response_url=yarl.URL(self._AUTHORITY))
        self._session_cookie = value

    def _update_session_cookie(self, response: aiohttp.ClientResponse) -> None:
        origin = yarl.URL(self._AUTHORITY)
        hostname = origin.host or ''
        for received in (*response.history, response):
            if received.url.origin() != origin.origin():
                continue
            cookie = received.cookies.get(self._AUTH_COOKIE_NAME)
            if cookie is None:
                continue
            domain = cookie['domain'].lstrip('.')
            if domain and hostname != domain and not hostname.endswith('.' + domain):
                continue
            if cookie.value:
                try:
                    user_id = self._decode_user_id(cookie.value)
                except UnknownBackendResponse:
                    logger.warning("Ignoring a renewed Humble session with an invalid user identity")
                    if self._session_cookie is not None:
                        self._set_session_cookie(self._session_cookie)
                    continue
                if str(user_id) != str(self._user_id):
                    logger.warning("Ignoring a renewed Humble session for a different account")
                    if self._session_cookie is not None:
                        self._set_session_cookie(self._session_cookie)
                    continue
            # Replace the old cookie even when Humble changes its domain scope.
            self._session.cookie_jar.clear(lambda item: item.key == self._AUTH_COOKIE_NAME)
            self._session.cookie_jar.update_cookies(
                {self._AUTH_COOKIE_NAME: cookie}, response_url=received.url
            )
            active = self._session.cookie_jar.filter_cookies(origin.join(yarl.URL(self._ORDER_LIST_URL)))
            current = active.get(self._AUTH_COOKIE_NAME)
            self._session_cookie = current.value if current and current.value else None
            if self._session_cookie is None:
                self._authenticated = False

    def _save_session_cookie(self) -> None:
        if not self.is_authenticated or self._credentials_callback is None:
            return
        if self._session_cookie == self._last_stored_cookie:
            return
        self._credentials_callback({'name': self._AUTH_COOKIE_NAME, 'value': self._session_cookie})
        self._last_stored_cookie = self._session_cookie

    async def _request(self, method, path, *args, **kwargs):
        url = self._AUTHORITY + path
        logger.debug("Humble request: method=%s", method)
        raise_for_status = kwargs.pop('raise_for_status', True)
        with handle_exception():
            response = await self._session.request(method, url, *args, raise_for_status=False, **kwargs)
            if response.status >= 400:
                logger.warning("Humble HTTP request rejected: method=%s, status=%d", method, response.status)
                if response.status == HTTPStatus.UNAUTHORIZED:
                    self._authenticated = False
            else:
                self._update_session_cookie(response)
                self._save_session_cookie()
            if raise_for_status:
                response.raise_for_status()
            return response

    async def _validate_authentication(self) -> None:
        """Raises galaxy.api.errors.AuthenticationRequired when session got invalidated."""
        with handle_exception():
            response = await self._request('get', self._ORDER_LIST_URL, raise_for_status=False)
            try:
                response.raise_for_status()
            finally:
                response.release()

    def _decode_user_id(self, _simpleauth_sess) -> str:
        try:
            info = _simpleauth_sess.split('|')[0]
            info += '=='  # Base64 decoding expects padded input.
            decoded = json.loads(base64.b64decode(info))
            user_id = decoded['user_id']
            if isinstance(user_id, bool) or not isinstance(user_id, (str, int)) or not str(user_id):
                raise ValueError()
            return str(user_id)
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise UnknownBackendResponse("Humble session has an invalid user identity") from None

    async def authenticate(self, auth_cookie: dict) -> str:
        self._authenticated = False
        self._user_id = None
        self._last_stored_cookie = None
        if not isinstance(auth_cookie, dict) or auth_cookie.get('name') != self._AUTH_COOKIE_NAME:
            raise AuthenticationRequired()
        if not isinstance(auth_cookie.get('value'), str) or not auth_cookie['value']:
            raise AuthenticationRequired()
        # Rebuild the original cookie object.
        try:
            cookie_val = bytes(auth_cookie['value'], "utf-8").decode("unicode_escape")
            # Some cookie values contain escaped characters while others do not.
            # Strip quotes from the escaped form.
            cookie_val = cookie_val.replace('"', '')
            user_id = self._decode_user_id(cookie_val)
        except (UnknownBackendResponse, UnicodeError):
            raise AuthenticationRequired() from None
        self._user_id = user_id
        self._set_session_cookie(cookie_val)
        await self._validate_authentication()
        if self._session_cookie is None:
            raise AuthenticationRequired()
        self._authenticated = True
        self._save_session_cookie()
        return user_id

    async def get_gamekeys(self) -> t.List[str]:
        res = await self._request('get', self._ORDER_LIST_URL)
        parsed = await res.json()
        logger.info(f"The order list:\n{parsed}")
        gamekeys = [it["gamekey"] for it in parsed]
        return gamekeys

    async def get_order_details(self, gamekey) -> dict:
        res = await self._request('get', self._ORDER_URL.format(gamekey), params={
            'all_tpkds': 'true'
        })
        return await res.json()
    
    async def get_orders_bulk_details(self, gamekeys: t.Iterable) -> t.Dict[str, dict]:
        params = [('all_tpkds', 'true')] + [('gamekeys', gk) for gk in gamekeys]
        res = await self._request('get', self._ORDERS_BULK_URL, params=params)
        return await res.json()

    async def get_subscription_products_with_gamekeys(self) -> t.AsyncGenerator[dict, None]:
        """
        Yield subscription products that expose Humble game keys.

        Choice entries expose unlocked months through `gamekey` and `contentChoicesMade`.
        Monthly entries expose subscribed months through `download_url`.
        """
        cursor = ''
        while True:
            res = await self._request('GET', self._SUBSCRIPTION_PRODUCTS + f"/{cursor}", raise_for_status=False)
            if res.status == 404:  # The API returns 404 when the subscription list is exhausted.
                return
            with handle_exception():
                res.raise_for_status()
            res_json = await res.json()
            for product in res_json['products']:
                yield product
            cursor = res_json['cursor']

    async def get_subscription_history(self, from_product: str) -> aiohttp.ClientResponse:
        """
        Marketing data of previous subscription months.
        :param from_product: machine_name of subscription following requested months
        for example 'february_2020_choice' to got a few month data items including
        'january_2020_choice', 'december_2019_choice', 'december_2020_monthly'
        """
        return await self._request('GET', self._SUBSCRIPTION_HISTORY.format(from_product), raise_for_status=False)

    async def get_previous_subscription_months(self, from_product: str):
        """Generator wrapper for get_subscription_history previous months"""
        while True:
            res = await self.get_subscription_history(from_product)
            if res.status == 404:
                return
            with handle_exception():
                res.raise_for_status()
            data = await res.json()
            previous_months = data.get('previous_months')
            if not isinstance(previous_months, list) or not previous_months:
                return
            for prev_month in previous_months:
                if not isinstance(prev_month, dict):
                    continue
                yield ChoiceMonth(prev_month)
            last_month = previous_months[-1]
            if not isinstance(last_month, dict):
                return
            machine_name = last_month.get('machine_name')
            if not isinstance(machine_name, str):
                return
            from_product = machine_name

    async def _get_webpack_data(self, path: str, webpack_id: str) -> dict:
        res = await self._request('GET', path)
        txt = await res.text()
        search = f'<script id="{webpack_id}" type="application/json">'
        json_start = txt.find(search) + len(search)
        candidate = txt[json_start:].strip()
        try:
            parsed, _ = json.JSONDecoder().raw_decode(candidate)
            return parsed
        except json.JSONDecodeError as e:
            raise WebpackParseError() from e
    
    async def get_user_subscription_state(self) -> dict:
        """
        for not subscriber:
        {"newestOwnedTier": null, "nextBilledPlan": "", "consecutiveContentDropCount": 0, "canResubscribe": false, "currentlySkippingContentHumanName": null, "perksStatus": "inactive", "billDate": "2021-11-30T18:00:00", "monthlyNewestOwnedContentMachineName": null, "willReceiveFutureMonths": false, "monthlyOwnsActiveContent": false, "unpauseDt": "2021-12-07T18:00:00", "creditsRemaining": 0, "currentlySkippingContentMachineName": null, "canBeConvertedFromGiftSubToPayingSub": false, "lastSkippedContentMachineName": null, "contentEndDateAfterBillDate": "2021-12-07T18:00:00", "isPaused": false, "monthlyNewestOwnedContentGamekey": null, "failedBillingMonths": 0, "wasPaused": false, "monthlyPurchasedAnyContent": false, "monthlyNewestOwnedContentEnd": null, "monthlyOwnsAnyContent": false, "monthlyNewestSkippedContentEnd": null}
        ---
        for subscriber with not unlocked active content:
        {"newestOwnedTier": "basic", "nextBilledPlan": "monthly_v2_basic", "consecutiveContentDropCount": 12, "canResubscribe": false, "currentlySkippingContentHumanName": null, "perksStatus": "active", "billDate": "2021-11-30T18:00:00", "monthlyNewestOwnedContentMachineName": "october_2021_choice", "willReceiveFutureMonths": true, "monthlyOwnsActiveContent": false, "unpauseDt": "2021-12-07T18:00:00", "creditsRemaining": 0, "currentlySkippingContentMachineName": null, "canBeConvertedFromGiftSubToPayingSub": false, "lastSkippedContentMachineName": "january_2021_choice", "contentEndDateAfterBillDate": "2021-12-07T18:00:00", "isPaused": false, "monthlyNewestOwnedContentGamekey": "***", "failedBillingMonths": 0, "monthlyNewestSkippedContentEnd": "2021-02-05T18:00:00", "wasPaused": false, "monthlyPurchasedAnyContent": true, "monthlyNewestOwnedContentEnd": "2021-11-02T17:00:00", "monthlyOwnsAnyContent": true)}
        ---
        at the time of creating this method, this data is attached to every humble page
        {}
        ---
        for subscriber at 2022-03:
        {"newestOwnedTier": "premium", "nextBilledPlan": "monthly_v2_premium", "consecutiveContentDropCount": 1, "canResubscribe": false, "currentlySkippingContentHumanName": null, "perksStatus": "active", "billDate": "2022-04-26T17:00:00", "monthlyNewestOwnedContentMachineName": "march_2022_choice", "willReceiveFutureMonths": true, "monthlyOwnsActiveContent": true, "unpauseDt": "2022-05-03T17:00:00", "creditsRemaining": 0, "currentlySkippingContentMachineName": null, "canBeConvertedFromGiftSubToPayingSub": false, "lastSkippedContentMachineName": null, "contentEndDateAfterBillDate": "2022-05-03T17:00:00", "isPaused": false, "monthlyNewestOwnedContentGamekey": "***", "failedBillingMonths": 0, "monthlyNewestSkippedContentEnd": null, "wasPaused": false, "monthlyPurchasedAnyContent": true, "monthlyNewestOwnedContentEnd": "2022-04-05T17:00:00", "monthlyOwnsAnyContent": true}
        """
        return await self._get_window_models(self._MAIN_PAGE, "userSubscriptionState")
    
    async def _get_window_models(self, path: str, model_name: str) -> dict:
        res = await self._request('GET', path)
        txt = await res.text()
        search = f'window.models.{model_name} = '
        json_start = txt.find(search) + len(search)
        candidate = txt[json_start:].strip()
        try:
            parsed, _ = json.JSONDecoder().raw_decode(candidate)
            return parsed
        except json.JSONDecodeError as e:
            raise WebpackParseError() from e
        
    async def get_subscriber_hub_data(self) -> dict:
        """
        Raises `WebpackParseError` when user was never a subscriber
        """
        webpack_id = "webpack-subscriber-hub-data"
        try:
            return await self._get_webpack_data(self._SUBSCRIPTION_HOME, webpack_id)
        except WebpackParseError:
            logger.warning("Cannot get subscriber info: probably user has never been a subscriber")
            raise

    async def get_main_page_webpack_data(self) -> dict:
        webpack_id = "webpack-json-data"
        return await self._get_webpack_data(self._MAIN_PAGE, webpack_id)

    async def get_choice_marketing_data(self) -> dict:
        """Parsing ~155K and fast response from server"""
        webpack_id = "webpack-choice-marketing-data"
        return await self._get_webpack_data(self._SUBSCRIPTION, webpack_id)

    async def get_choice_content_data(self, product_url_path) -> ChoiceContentData:
        """Parsing ~220K
        product_url_path: last element of choice subscripiton url for example 'february-2020'
        """
        url = self._SUBSCRIPTION + '/' + product_url_path
        webpack_id = 'webpack-monthly-product-data'
        data = await self._get_webpack_data(url, webpack_id)
        return ChoiceContentData(data)

    async def get_montly_content_data(self, product_url_path) -> MontlyContentData:
        """
        product_url_path: last element of subscripiton url for example 'august_2019_monthly'
        """
        url = 'monthly/p/' + product_url_path
        webpack_id = 'webpack-monthly-product-data'
        data = await self._get_webpack_data(url, webpack_id)
        return MontlyContentData(data)

    async def sign_download(self, machine_name: str, filename: str):
        res = await self._request('post', self._DOWNLOAD_SIGN, params={
            'machine_name': machine_name,
            'filename': filename
        })
        return await res.json()
    
    async def _reedem_download(self, download_machine_name: str, custom_data: dict):
        """Redeem a download using the signed URL flow and expect a success response."""
        params = {
            'download': download_machine_name,
            'download_page': "false",  # The API expects this flag to be false for download pages.
        }
        params.update(custom_data)
        res = await self._request('post', self._HUMBLER_REDEEM_DOWNLOAD, params=params)
        content = await res.read()
        if content != b"{'success': True}":
            raise UnknownBackendResponse(f'unexpected response while reedem trove download: {content}')

    @staticmethod
    def _filename_from_web_link(link: str):
        return yarl.URL(link).parts[-1]

    async def sign_url_subproduct(self, download: DownloadStructItem, download_machine_name: str):
        if download.web is None:
            raise RuntimeError(f'No download web link in download struct item {download}')
        filename = self._filename_from_web_link(download.web)
        urls = await self.sign_download(download_machine_name, filename)
        try:
            await self._reedem_download(
                download_machine_name, {'download_url_file': filename})
        except Exception as e:
            logger.error(repr(e) + '. Error ignored')
        return urls

    async def close_session(self):
        await self._session.close()
