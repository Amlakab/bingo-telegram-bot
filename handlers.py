from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import re
from api_client import api
from config import config
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Conversation states
REGISTER_PHONE, REGISTER_PASSWORD, REGISTER_CONFIRM_PASSWORD = range(3)
DEPOSIT_AMOUNT, DEPOSIT_METHOD, DEPOSIT_VERIFICATION = range(3, 6)
WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_ACCOUNT, WITHDRAW_NAME = range(6, 10)

class BingoBotHandlers:
    def __init__(self):
        self.user_sessions = {}

    def get_user_id(self, telegram_id):
        session = self.user_sessions.get(telegram_id)
        return session.get('user_id') if session else None

    def get_user_data(self, telegram_id):
        session = self.user_sessions.get(telegram_id)
        return session.get('user_data') if session else None

    def is_authenticated(self, telegram_id):
        session = self.user_sessions.get(telegram_id)
        return session and session.get('token') is not None

    def format_currency(self, amount):
        return f"{amount:,.2f} ETB"

    # ==================== KEYBOARDS ====================

    def get_persistent_reply_keyboard(self, is_auth=True):
        """Returns full keyboard for authenticated users, or a single Register button for guests."""
        if is_auth:
            keyboard = [
                [KeyboardButton("🎮 Play Bingo")],
                [
                    KeyboardButton("💰 Deposit"),
                    KeyboardButton("💸 Withdraw"),
                    KeyboardButton("📩 Transfer")
                ],
                [
                    KeyboardButton("💰 Balance"),
                    KeyboardButton("📜 Transactions")
                ],
                [
                    KeyboardButton("ℹ️ Info"),
                    KeyboardButton("🎁 Invite")
                ]
            ]
        else:
            keyboard = [
                [KeyboardButton("📝 Register")]
            ]
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True
        )

    def get_deposit_keyboard(self):
        keyboard = [
            [
                InlineKeyboardButton("📱 Telebirr", callback_data='deposit_telebirr'),
                InlineKeyboardButton("🏦 CBE Birr", callback_data='deposit_cbe')
            ],
            [
                InlineKeyboardButton("🏛️ Awash Bank", callback_data='deposit_awash'),
                InlineKeyboardButton("💳 CBE", callback_data='deposit_cbe_bank')
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_withdraw_keyboard(self):
        keyboard = [
            [
                InlineKeyboardButton("📱 Telebirr", callback_data='withdraw_telebirr'),
                InlineKeyboardButton("🏦 CBE Birr", callback_data='withdraw_cbe')
            ],
            [
                InlineKeyboardButton("🏛️ Awash Bank", callback_data='withdraw_awash'),
                InlineKeyboardButton("💳 CBE", callback_data='withdraw_cbe_bank')
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_register_inline_keyboard(self):
        keyboard = [
            [InlineKeyboardButton("📝 Click Here to Register", callback_data='register')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_cancel_inline_keyboard(self):
        keyboard = [
            [InlineKeyboardButton("❌ Cancel Operation", callback_data='cancel')]
        ]
        return InlineKeyboardMarkup(keyboard)

    # ==================== START & MENU ====================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if self.is_authenticated(telegram_id):
            user_data = self.get_user_data(telegram_id)
            if not user_data:
                api.set_token(self.user_sessions[telegram_id]['token'])
                response = api.get_user_profile()
                if response['success']:
                    user_data = response['data']
                    self.user_sessions[telegram_id]['user_data'] = user_data

            content = (
                f"👋 *Welcome back, {user_data.get('first_name', user.first_name or 'User')}!*\n\n"
                f"💰 *Balance:* {self.format_currency(user_data.get('wallet', 0))}\n"
                f"📱 *Phone:* {user_data.get('phone', 'N/A')}\n\n"
                "Select an option from the bottom menu to continue."
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode='Markdown',
                reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
            )
        else:
            content = (
                "🎯 *Welcome to Feta Bingo Bot!*\n\n"
                "You are currently not registered. Please click Register to start playing and winning real money!\n\n"
                "✨ *Features:*\n"
                "• 🎮 Play exciting Bingo games\n"
                "• 💰 Deposit and withdraw funds\n"
                "• 📊 Track your earnings\n"
                "• 🏆 Win real money"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode='Markdown',
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False)
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="👇 Tap below to register:",
                reply_markup=self.get_register_inline_keyboard()
            )

    # ==================== REGISTER ====================

    async def register_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if self.is_authenticated(telegram_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ You are already registered and logged in!",
                reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
            )
            return ConversationHandler.END

        content = "📝 *Registration*\n\nPlease enter your phone number (format: 09XXXXXXXX or 07XXXXXXXX):"
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return REGISTER_PHONE

    async def register_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return REGISTER_PHONE

        phone = update.message.text.strip()
        chat_id = update.effective_chat.id

        if not re.match(r'^(09|07)\d{8}$', phone):
            content = "❌ Invalid phone number format.\nPlease use format: 09XXXXXXXX or 07XXXXXXXX"
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return REGISTER_PHONE

        context.user_data['register_phone'] = phone
        content = "Now enter a password (minimum 6 characters):"
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return REGISTER_PASSWORD

    async def register_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return REGISTER_PASSWORD

        password = update.message.text.strip()
        chat_id = update.effective_chat.id

        if len(password) < 6:
            content = "❌ Password must be at least 6 characters.\n\nEnter a password (minimum 6 characters):"
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return REGISTER_PASSWORD

        context.user_data['register_password'] = password
        content = "Confirm your password:"
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return REGISTER_CONFIRM_PASSWORD

    async def register_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return REGISTER_CONFIRM_PASSWORD

        confirm_password = update.message.text.strip()
        password = context.user_data.get('register_password')
        phone = context.user_data.get('register_phone')
        telegram_id = str(update.effective_user.id)
        chat_id = update.effective_chat.id

        if password != confirm_password:
            content = "❌ Passwords do not match.\n\nPlease confirm your password:"
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return REGISTER_CONFIRM_PASSWORD

        username = update.effective_user.username
        first_name = update.effective_user.first_name

        if username:
            tg_id = username.replace('@', '').strip()
            if len(tg_id) < 4:
                tg_id = f"user_{telegram_id}"
            elif len(tg_id) > 31:
                tg_id = tg_id[:31]
        else:
            tg_id = telegram_id

        response = api.register_user(phone=phone, password=password, tg_id=tg_id)

        if response['success']:
            data = response['data']
            token = data.get('token')
            user_data = data.get('user', {})

            if token and user_data:
                self.user_sessions[telegram_id] = {
                    'user_id': user_data.get('_id'),
                    'token': token,
                    'user_data': user_data,
                    'phone': phone
                }
                api.set_token(token)

                content = (
                    f"🎉 *Registration successful!*\n\n"
                    f"Welcome {first_name or 'User'}!\n"
                    f"💰 Balance: {self.format_currency(user_data.get('wallet', 0))}\n"
                    f"📱 Phone: {phone}\n\n"
                    "Your main menu is now unlocked below!"
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    parse_mode='Markdown',
                    reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
                )
                context.user_data.clear()
                return ConversationHandler.END

        error_msg = response.get('message', 'Registration failed')
        content = f"❌ Registration failed: {error_msg}"
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=self.get_persistent_reply_keyboard(is_auth=False)
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ==================== PLAY BINGO ====================

    async def play_bingo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Play Bingo - Generate one-time code and send link"""
        query = update.callback_query
        if query:
            await query.answer()
        
        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        
        if not self.is_authenticated(telegram_id):
            content = "❌ Please register first with /register"
            await self.update_content(update.get_bot(), chat_id, content)
            await self.update_menu(update.get_bot(), chat_id, "📝 *Register*", self.get_register_keyboard())
            return
        
        user_data = self.get_user_data(telegram_id)
        if not user_data:
            api.set_token(self.user_sessions[telegram_id]['token'])
            response = api.get_user_profile()
            if response['success']:
                user_data = response['data']
                self.user_sessions[telegram_id]['user_data'] = user_data
        
        user_id = self.user_sessions[telegram_id].get('user_id')
        
        # Generate one-time code from backend
        code_response = api.generate_game_code(user_id)
        
        if not code_response['success']:
            content = "❌ Failed to generate game link. Please try again."
            await self.update_content(update.get_bot(), chat_id, content)
            await self.update_menu(update.get_bot(), chat_id, "📱 *Main Menu*", self.get_main_menu_keyboard())
            return
        
        code = code_response['data']['code']
        
        # Bingo game URL with one-time code
        bingo_url = f"https://addis-bingo-game-client.vercel.app/user/lobby?code={code}"
        
        # Send only the link
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎮 Play Bingo: {bingo_url}"
        )

    # ==================== DEPOSIT ====================

    async def deposit_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if not self.is_authenticated(telegram_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please register first to deposit funds.",
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False)
            )
            return ConversationHandler.END

        content = (
            "💰 *Deposit Funds*\n\n"
            "• Minimum deposit: 10 ETB\n"
            "• Bonus: 10% for deposits above 50 ETB\n\n"
            "የ ክፍያ አይነት ይምረጡ 👇👇👇👇👇"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_deposit_keyboard()
        )
        return DEPOSIT_METHOD

    async def deposit_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return

        await query.answer()
        method = query.data.replace('deposit_', '')
        context.user_data['deposit_method'] = method
        chat_id = update.effective_chat.id
        telegram_id = str(query.from_user.id)

        method_names = {
            'telebirr': '📱 Telebirr',
            'cbe': '🏦 CBE Birr',
            'awash': '🏛️ Awash Bank',
            'cbe_bank': '💳 CBE'
        }
        method_display = method_names.get(method, method.upper())

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_accountants(blocked=False)

        if not response['success'] or not response['data']:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ No deposit payment details currently available. Please try again later."
            )
            return ConversationHandler.END

        accountants = response['data']
        accountant = next((acc for acc in accountants if method in acc.get('bankName', '').lower()), accountants[0])
        context.user_data['deposit_accountant'] = accountant

        if method == 'telebirr':
            details = f"📱 *Phone:* {accountant.get('phoneNumber', 'N/A')}"
        else:
            details = f"🏦 *Account:* {accountant.get('accountNumber', 'N/A')}\n👤 *Name:* {accountant.get('fullName', 'N/A')}"

        content = (
            f"💰 *Deposit via {method_display}*\n\n"
            f"{details}\n\n"
            f"⚠️ *Manual Review Required*\n"
            f"Please enter the amount you want to deposit (min: 10 ETB):"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return DEPOSIT_AMOUNT

    async def deposit_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return DEPOSIT_AMOUNT

        chat_id = update.effective_chat.id

        try:
            amount = float(update.message.text.strip())
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please enter a valid numerical amount:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return DEPOSIT_AMOUNT

        if amount < 10:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Minimum deposit is 10 ETB. Please enter a valid amount:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return DEPOSIT_AMOUNT

        context.user_data['deposit_amount'] = amount
        bonus = amount * 0.10 if amount > 50 else 0
        total = amount + bonus

        content = (
            f"✅ *Amount:* {self.format_currency(amount)}\n"
            f"🎁 *Bonus:* {self.format_currency(bonus)}\n"
            f"💰 *Total Credit:* {self.format_currency(total)}\n\n"
            f"Please enter your transaction reference / ID:"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return DEPOSIT_VERIFICATION

    async def deposit_verify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return DEPOSIT_VERIFICATION

        transaction_id = update.message.text.strip()
        chat_id = update.effective_chat.id

        if not transaction_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please enter a valid transaction ID:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return DEPOSIT_VERIFICATION

        amount = context.user_data.get('deposit_amount')
        accountant = context.user_data.get('deposit_accountant')
        method = context.user_data.get('deposit_method')
        telegram_id = str(update.effective_user.id)
        user_data = self.user_sessions[telegram_id]['user_data']

        bonus = amount * 0.10 if amount > 50 else 0
        total = amount + bonus

        deposit_data = {
            'userId': user_data.get('_id'),
            'amount': total,
            'type': 'deposit',
            'reference': f"DEP-{telegram_id}-{int(datetime.now().timestamp())}",
            'description': f"Deposit via {method.upper()} (Bonus: {bonus})",
            'transactionId': transaction_id,
            'senderPhone': user_data.get('phone'),
            'senderName': user_data.get('first_name', 'User'),
            'receiverPhone': accountant.get('phoneNumber') if method == 'telebirr' else accountant.get('accountNumber'),
            'receiverName': accountant.get('fullName'),
            'method': method
        }

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.create_transaction(deposit_data)

        if response['success']:
            content = (
                f"✅ *Deposit submitted!*\n\n"
                f"💰 Amount: {self.format_currency(amount)}\n"
                f"🎁 Bonus: {self.format_currency(bonus)}\n"
                f"💰 Total: {self.format_currency(total)}\n"
                f"📱 Method: {method.upper()}\n\n"
                f"⏳ Your deposit will be credited after manual review."
            )
        else:
            content = f"❌ Deposit submission failed: {response.get('message', 'Unknown error')}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ==================== WITHDRAW ====================

    async def withdraw_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if not self.is_authenticated(telegram_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please register first to make withdrawals.",
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False)
            )
            return ConversationHandler.END

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_user_profile()

        if response['success']:
            user_data = response['data']
            self.user_sessions[telegram_id]['user_data'] = user_data
        else:
            user_data = self.get_user_data(telegram_id)

        content = (
            f"💳 *Withdraw Funds*\n\n"
            f"💰 *Available Balance:* {self.format_currency(user_data.get('wallet', 0))}\n"
            f"💳 *Minimum Withdrawal:* {self.format_currency(100)}\n\n"
            f"Select your withdrawal method below:"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_withdraw_keyboard()
        )
        return WITHDRAW_METHOD

    async def withdraw_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return

        await query.answer()
        method = query.data.replace('withdraw_', '')
        context.user_data['withdraw_method'] = method
        chat_id = update.effective_chat.id

        method_names = {
            'telebirr': '📱 Telebirr',
            'cbe': '🏦 CBE Birr',
            'awash': '🏛️ Awash Bank',
            'cbe_bank': '💳 CBE'
        }
        method_display = method_names.get(method, method.upper())

        content = f"💳 *Withdraw via {method_display}*\n\nPlease enter the amount you wish to withdraw (min: 100 ETB):"
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return WITHDRAW_AMOUNT

    async def withdraw_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return WITHDRAW_AMOUNT

        chat_id = update.effective_chat.id

        try:
            amount = float(update.message.text.strip())
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please enter a valid number:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return WITHDRAW_AMOUNT

        if amount < 100:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Minimum withdrawal amount is 100 ETB. Please re-enter amount:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return WITHDRAW_AMOUNT

        telegram_id = str(update.effective_user.id)
        user_data = self.user_sessions[telegram_id]['user_data']
        balance = user_data.get('wallet', 0)

        if amount > balance:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Insufficient balance. Available balance is {self.format_currency(balance)}. Enter a smaller amount:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return WITHDRAW_AMOUNT

        context.user_data['withdraw_amount'] = amount
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"💳 *Amount:* {self.format_currency(amount)}\n\nPlease enter your account/phone number for withdrawal:",
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return WITHDRAW_ACCOUNT

    async def withdraw_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return WITHDRAW_ACCOUNT

        account = update.message.text.strip()
        chat_id = update.effective_chat.id

        if not account:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Invalid account. Please enter your account number:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return WITHDRAW_ACCOUNT

        context.user_data['withdraw_account'] = account
        await context.bot.send_message(
            chat_id=chat_id,
            text="Enter full account holder name:",
            reply_markup=self.get_cancel_inline_keyboard()
        )
        return WITHDRAW_NAME

    async def withdraw_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return WITHDRAW_NAME

        name = update.message.text.strip()
        chat_id = update.effective_chat.id

        if not name:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please enter a valid account holder name:",
                reply_markup=self.get_cancel_inline_keyboard()
            )
            return WITHDRAW_NAME

        amount = context.user_data.get('withdraw_amount')
        method = context.user_data.get('withdraw_method')
        account = context.user_data.get('withdraw_account')
        telegram_id = str(update.effective_user.id)
        user_data = self.user_sessions[telegram_id]['user_data']

        api.set_token(self.user_sessions[telegram_id]['token'])
        accountants_response = api.get_accountants(blocked=False)
        accountant = None
        if accountants_response['success'] and accountants_response['data']:
            accountant = next((acc for acc in accountants_response['data'] if method in acc.get('bankName', '').lower()), accountants_response['data'][0])

        withdrawal_data = {
            'userId': user_data.get('_id'),
            'amount': amount,
            'type': 'withdrawal',
            'reference': f"WTH-{telegram_id}-{int(datetime.now().timestamp())}",
            'description': f"Withdrawal via {method.upper()}",
            'senderPhone': accountant.get('phoneNumber') if accountant else '',
            'senderName': accountant.get('fullName') if accountant else '',
            'receiverPhone': account,
            'receiverName': name,
            'method': method
        }

        response = api.create_transaction(withdrawal_data)

        if response['success']:
            content = (
                f"✅ *Withdrawal request submitted!*\n\n"
                f"💰 Amount: {self.format_currency(amount)}\n"
                f"📱 Method: {method.upper()}\n"
                f"📱 Account: {account}\n"
                f"👤 Name: {name}\n\n"
                f"⏳ Processed following manual verification."
            )
        else:
            content = f"❌ Withdrawal failed: {response.get('message', 'Unknown error')}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ==================== BALANCE ====================

    async def show_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if not self.is_authenticated(telegram_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please register first to check balance.",
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False)
            )
            return

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_user_profile()

        if response['success']:
            user_data = response['data']
            self.user_sessions[telegram_id]['user_data'] = user_data

            content = (
                f"📊 *Your Balance*\n\n"
                f"💰 *Balance:* {self.format_currency(user_data.get('wallet', 0))}\n"
                f"📈 *Daily Earnings:* {self.format_currency(user_data.get('dailyEarnings', 0))}\n"
                f"📊 *Weekly Earnings:* {self.format_currency(user_data.get('weeklyEarnings', 0))}\n"
                f"🏆 *Total Earnings:* {self.format_currency(user_data.get('totalEarnings', 0))}\n\n"
                f"💳 Minimum Withdrawal: {self.format_currency(100)}\n"
                f"💵 Maximum Deposit: {self.format_currency(10000)}"
            )
        else:
            content = f"❌ Failed to fetch balance: {response['message']}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
        )

    # ==================== HISTORY ====================

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if not self.is_authenticated(telegram_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Please register first to view transaction history.",
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False)
            )
            return

        user_data = self.user_sessions[telegram_id]['user_data']
        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_transactions(user_data.get('_id'), limit=10)

        if not response['success']:
            content = f"❌ Failed to fetch transactions: {response['message']}"
        else:
            transactions = response['data']
            if not transactions:
                content = "📝 No transactions found."
            else:
                content = "📝 *Transaction History*\n\n"
                for tx in transactions[:10]:
                    emoji = "🟢" if tx['type'] in ['deposit', 'winning'] else "🔴"
                    status_emoji = "✅" if tx['status'] == 'completed' else "⏳" if tx['status'] == 'pending' else "❌"

                    tx_date = tx.get('createdAt', tx.get('date', ''))
                    if tx_date:
                        try:
                            tx_date = datetime.fromisoformat(tx_date.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M')
                        except:
                            tx_date = str(tx_date)[:16]
                    else:
                        tx_date = 'N/A'

                    content += f"{emoji} *{tx['type'].upper()}* {status_emoji}\n"
                    content += f"   Amount: {self.format_currency(tx['amount'])}\n"
                    content += f"   Status: {tx['status'].upper()}\n"
                    content += f"   📅 {tx_date}\n\n"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True)
        )

    # ==================== INFO ====================

    async def show_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)

        content = (
            "ℹ️ *How to Play Bingo*\n\n"
            "1️⃣ *Register* - Create your account with phone and password\n"
            "2️⃣ *Deposit* - Add funds using Telebirr, CBE Birr, Awash Bank, or CBE\n"
            "   • Minimum deposit: 10 ETB\n"
            "   • Bonus: 10% for deposits above 50 ETB\n"
            "3️⃣ *Play Bingo* - Join a game and mark numbers on your card\n"
            "4️⃣ *Win* - Complete a pattern to win real money\n"
            "5️⃣ *Withdraw* - Cash out your winnings anytime"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=self.is_authenticated(telegram_id))
        )

    # ==================== INVITE ====================

    async def show_invite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        is_auth = self.is_authenticated(telegram_id)

        user_id = self.user_sessions.get(telegram_id, {}).get('user_id', '')
        bot_username = "fetta_bingo_bot"
        invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"

        content = (
            "🎁 *Invite Friends*\n\n"
            "Share your link with friends to earn rewards!\n\n"
            f"🔗 *Your Invite Link:*\n`{invite_link}`"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=is_auth)
        )

    # ==================== TRANSFER ====================

    async def show_transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)

        content = "📩 *Transfer Funds*\n\nPlayer-to-player transfers are coming soon!"
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=self.is_authenticated(telegram_id))
        )

    # ==================== CANCEL ====================

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        if update.callback_query:
            await update.callback_query.answer()

        is_auth = self.is_authenticated(telegram_id)
        content = "❌ Operation cancelled."
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=self.get_persistent_reply_keyboard(is_auth=is_auth)
        )

        context.user_data.clear()
        return ConversationHandler.END