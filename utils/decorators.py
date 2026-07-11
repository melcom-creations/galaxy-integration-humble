import asyncio
from contextlib import suppress
from functools import wraps
from typing import Any, Callable, Optional, Union


def double_click_effect(timeout: float, effect: Union[Callable, str], *effect_args, **effect_kwargs):
    """
    Decorator of asynchronious function that allows to call synchonious `effect` 
    if the function was called second time within `timeout` seconds
    ---
    To decorate methods of class instances, `effect` should be str matching the method name.
    """
    def _wrapper(fn):
        task: Optional[asyncio.Task[Any]] = None

        @wraps(fn)
        async def wrap(*args, **kwargs):
            nonlocal task

            async def delayed_fn():
                await asyncio.sleep(timeout)
                await fn(*args, **kwargs)

            if task is None or task.done() or task.cancelled():
                task = asyncio.create_task(delayed_fn())
                with suppress(asyncio.CancelledError):
                    await task
            else:
                task.cancel()
                if isinstance(effect, str):  # for class methods args[0] is `self`
                    return getattr(args[0], effect)(*effect_args, **effect_kwargs)
                else:
                    return effect(*effect_args, **effect_kwargs)
        return wrap
    return _wrapper
