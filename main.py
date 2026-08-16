#!/usr/bin/env python3
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from telegram import Update, BotCommand
from handlers import BingoBotHandlers
from handlers import (
    REGISTER_PHONE, REGISTER_PASSWORD, REGISTER_CONFIRM_PASSWORD,
    DEPOSIT_AMOUNT, DEPOSIT_METHOD, DEPOSIT_VERIFICATION,
    WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_ACCOUNT, WITHDRAW_NAME
)
from config import config
import logging
import sys
import warnings

warnings.filterwarnings("ignore")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Start or restart the bot"),
        BotCommand("menu", "Show main menu"),
        BotCommand("register", "Register account"),
        BotCommand("history", "View transactions"),
        BotCommand("cancel", "Cancel action")
    ]
    await application.bot.set_my_commands(commands)

def main():
    try:
        application = (
            Application.builder()
            .token(config.BOT_TOKEN)
            .post_init(post_init)
            .read_timeout(60)
            .write_timeout(60)
            .connect_timeout(60)
            .pool_timeout(60)
            .build()
        )

        handlers = BingoBotHandlers()

        # Registration Conversation
        register_conv = ConversationHandler(
            entry_points=[
                CommandHandler("register", handlers.register_start),
                CallbackQueryHandler(handlers.register_start, pattern='^register$'),
                MessageHandler(filters.Regex("^📝 Register$"), handlers.register_start)
            ],
            states={
                REGISTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.register_phone)],
                REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.register_password)],
                REGISTER_CONFIRM_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.register_confirm)],
            },
            fallbacks=[
                CommandHandler("cancel", handlers.cancel),
                CallbackQueryHandler(handlers.cancel, pattern='^cancel$')
            ]
        )

        # Deposit Conversation
        deposit_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(handlers.deposit_start, pattern='^deposit$'),
                MessageHandler(filters.Regex("^💰 Deposit$"), handlers.deposit_start)
            ],
            states={
                DEPOSIT_METHOD: [CallbackQueryHandler(handlers.deposit_method, pattern='^deposit_')],
                DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.deposit_amount)],
                DEPOSIT_VERIFICATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.deposit_verify)],
            },
            fallbacks=[
                CommandHandler("cancel", handlers.cancel),
                CallbackQueryHandler(handlers.cancel, pattern='^cancel$')
            ]
        )

        # Withdraw Conversation
        withdraw_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(handlers.withdraw_start, pattern='^withdraw$'),
                MessageHandler(filters.Regex("^💸 Withdraw$"), handlers.withdraw_start)
            ],
            states={
                WITHDRAW_METHOD: [CallbackQueryHandler(handlers.withdraw_method, pattern='^withdraw_')],
                WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.withdraw_amount)],
                WITHDRAW_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.withdraw_account)],
                WITHDRAW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.withdraw_name)],
            },
            fallbacks=[
                CommandHandler("cancel", handlers.cancel),
                CallbackQueryHandler(handlers.cancel, pattern='^cancel$')
            ]
        )

        # Register Conversations First
        application.add_handler(register_conv)
        application.add_handler(deposit_conv)
        application.add_handler(withdraw_conv)

        # Basic Commands
        application.add_handler(CommandHandler("start", handlers.start))
        application.add_handler(CommandHandler("menu", handlers.start))
        application.add_handler(CommandHandler("history", handlers.show_history))
        application.add_handler(CommandHandler("cancel", handlers.cancel))

        # Reply Keyboard Button Actions
        application.add_handler(MessageHandler(filters.Regex("^🎮 Play Bingo$"), handlers.play_bingo))
        # application.add_handler(MessageHandler(filters.Regex("^📩 Transfer$"), handlers.show_transfer))
        application.add_handler(MessageHandler(filters.Regex("^💰 Balance$"), handlers.show_balance))
        application.add_handler(MessageHandler(filters.Regex("^📜 Transactions$"), handlers.show_history))
        application.add_handler(MessageHandler(filters.Regex("^ℹ️ Info$"), handlers.show_info))
        application.add_handler(MessageHandler(filters.Regex("^🎁 Invite$"), handlers.show_invite))

        # Generic Inline Callbacks
        application.add_handler(CallbackQueryHandler(handlers.start, pattern='^menu$'))

        logger.info("🤖 Bot started! Your bot is live on Telegram.")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            poll_interval=1.0,
            timeout=60,
            read_timeout=60,
            write_timeout=60,
            connect_timeout=60
        )

    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()