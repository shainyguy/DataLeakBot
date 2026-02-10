from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from database.crud import UserCRUD, SubscriptionCRUD
from database.models import SubscriptionType
from bot.keyboards.subscription_kb import (
    get_subscription_plans_kb,
    get_payment_kb,
    get_manage_subscription_kb,
)
from bot.keyboards.main_kb import get_main_menu_kb
from bot.utils.helpers import (
    SUBSCRIPTION_TEXT,
    PAYMENT_SUCCESS_TEXT,
    format_subscription_name,
    format_date,
    is_subscription_active,
)
from payments.yookassa_pay import YooKassaService

router = Router()


@router.message(F.text == "💎 Подписка")
@router.message(Command("subscribe"))
async def cmd_subscription(message: Message, session: AsyncSession):
    """Показ тарифов"""
    user = await UserCRUD.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("Нажмите /start для начала работы.")
        return

    if is_subscription_active(user):
        await message.answer(
            f"📊 <b>Ваш текущий тариф:</b> "
            f"{format_subscription_name(user.subscription_type)}\n"
            f"📅 Действует до: {format_date(user.subscription_expires)}\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=get_manage_subscription_kb(),
        )
    else:
        await message.answer(
            SUBSCRIPTION_TEXT,
            parse_mode="HTML",
            reply_markup=get_subscription_plans_kb(),
        )


@router.callback_query(F.data == "subscription:show")
async def show_plans(callback: CallbackQuery):
    """Показ тарифов через callback"""
    await callback.message.edit_text(
        SUBSCRIPTION_TEXT,
        parse_mode="HTML",
        reply_markup=get_subscription_plans_kb(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("subscribe:"))
async def process_subscribe(callback: CallbackQuery, session: AsyncSession):
    """Создание платежа"""
    plan = callback.data.split(":")[1]

    if plan == "premium":
        sub_type = SubscriptionType.PREMIUM
    elif plan == "business":
        sub_type = SubscriptionType.BUSINESS
    else:
        await callback.answer("Неизвестный тариф", show_alert=True)
        return

    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка. Нажмите /start", show_alert=True)
        return

    try:
        # Создаём платёж в YooKassa
        payment_data = YooKassaService.create_payment(
            sub_type=sub_type,
            telegram_id=callback.from_user.id,
        )

        # Сохраняем в БД
        await SubscriptionCRUD.create_payment(
            session=session,
            user_id=user.id,
            payment_id=payment_data["payment_id"],
            sub_type=sub_type,
            amount=payment_data["amount"] * 100,  # в копейках
        )

        plan_info = YooKassaService.get_plan_info(sub_type)

        await callback.message.edit_text(
            f"💳 <b>Оформление подписки</b>\n\n"
            f"├ 📊 Тариф: {plan_info['title']}\n"
            f"├ 💰 Сумма: {payment_data['amount']}₽\n"
            f"├ 📅 Период: 1 месяц\n\n"
            f"Нажмите кнопку «Оплатить» для перехода "
            f"на страницу оплаты.\n\n"
            f"После оплаты нажмите «Я оплатил» ✅",
            parse_mode="HTML",
            reply_markup=get_payment_kb(
                payment_url=payment_data["payment_url"],
                payment_id=payment_data["payment_id"],
            ),
        )

    except Exception as e:
        await callback.message.edit_text(
            "❌ Ошибка при создании платежа. "
            "Попробуйте позже или обратитесь в поддержку.\n\n"
            f"Код ошибки: <code>{type(e).__name__}</code>",
            parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment_status(
    callback: CallbackQuery, session: AsyncSession
):
    """Проверка статуса платежа по кнопке «Я оплатил»"""
    payment_id = callback.data.split(":", 1)[1]

    try:
        payment_info = YooKassaService.check_payment(payment_id)

        if payment_info["paid"] and payment_info["status"] == "succeeded":
            # Подтверждаем платёж в БД
            sub = await SubscriptionCRUD.confirm_payment(
                session, payment_id
            )

            if sub:
                user = await UserCRUD.get_by_telegram_id(
                    session, callback.from_user.id
                )
                if user:
                    # Активируем подписку
                    await UserCRUD.activate_subscription(
                        session, user, sub.subscription_type
                    )

                    await callback.message.edit_text(
                        PAYMENT_SUCCESS_TEXT.format(
                            plan=format_subscription_name(
                                sub.subscription_type
                            ),
                            amount=sub.amount // 100,
                            expires=format_date(user.subscription_expires),
                        ),
                        parse_mode="HTML",
                    )
                    await callback.answer(
                        "✅ Подписка активирована!", show_alert=True
                    )
                    return

        elif payment_info["status"] == "pending":
            await callback.answer(
                "⏳ Платёж ещё обрабатывается. "
                "Подождите и попробуйте снова.",
                show_alert=True,
            )
            return

        elif payment_info["status"] == "canceled":
            await callback.message.edit_text(
                "❌ Платёж был отменён.\n"
                "Попробуйте оформить подписку заново.",
                parse_mode="HTML",
                reply_markup=get_subscription_plans_kb(),
            )
            await callback.answer()
            return

        await callback.answer(
            "⏳ Оплата ещё не поступила. Попробуйте позже.",
            show_alert=True,
        )

    except Exception as e:
        await callback.answer(
            f"❌ Ошибка проверки: {type(e).__name__}",
            show_alert=True,
        )


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    """Отмена оплаты"""
    await callback.message.edit_text(
        "❌ Оплата отменена.\n\n"
        "Вы всегда можете оформить подписку позже "
        "через меню «💎 Подписка».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "subscription:renew")
async def renew_subscription(callback: CallbackQuery, session: AsyncSession):
    """Продление подписки"""
    user = await UserCRUD.get_by_telegram_id(
        session, callback.from_user.id
    )
    if not user:
        await callback.answer("Ошибка")
        return

    sub_type = user.subscription_type
    if sub_type == SubscriptionType.FREE:
        await show_plans(callback)
        return

    try:
        payment_data = YooKassaService.create_payment(
            sub_type=sub_type,
            telegram_id=callback.from_user.id,
        )

        await SubscriptionCRUD.create_payment(
            session=session,
            user_id=user.id,
            payment_id=payment_data["payment_id"],
            sub_type=sub_type,
            amount=payment_data["amount"] * 100,
        )

        await callback.message.edit_text(
            f"🔄 <b>Продление подписки</b>\n\n"
            f"├ 📊 Тариф: "
            f"{format_subscription_name(sub_type)}\n"
            f"├ 💰 Сумма: {payment_data['amount']}₽\n\n"
            f"Нажмите «Оплатить» для продления:",
            parse_mode="HTML",
            reply_markup=get_payment_kb(
                payment_url=payment_data["payment_url"],
                payment_id=payment_data["payment_id"],
            ),
        )
    except Exception as e:
        await callback.answer(
            f"Ошибка: {type(e).__name__}", show_alert=True
        )

    await callback.answer()