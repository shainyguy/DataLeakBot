from aiogram import Router
from bot.handlers import (
    start,
    menu,
    profile,
    subscription,
    check,
    password,
    history,
    monitoring,
    family,
    business,
    admin,
)


def get_all_routers() -> list[Router]:
    return [
        start.router,
        menu.router,
        profile.router,
        subscription.router,
        check.router,
        password.router,
        history.router,
        monitoring.router,
        family.router,
        business.router,
        admin.router,
    ]