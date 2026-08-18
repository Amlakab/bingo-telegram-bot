import sqlite3  # ✅ Add this with other imports
import secrets
import string
import random  # If using the first version with random.shuffle
import asyncio  # ✅ Add this line
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
import re
from api_client import api
from config import config
import logging
from datetime import datetime
from rate_limiter import RateLimiter
from database import db  # ✅ ADD THIS LINE

logger = logging.getLogger(__name__)

# Conversation states
REGISTER_PHONE, REGISTER_PASSWORD, REGISTER_CONFIRM_PASSWORD = range(3)
DEPOSIT_AMOUNT, DEPOSIT_METHOD, DEPOSIT_VERIFICATION = range(3, 6)
WITHDRAW_AMOUNT, WITHDRAW_METHOD, WITHDRAW_ACCOUNT, WITHDRAW_NAME = range(6, 10)

class BingoBotHandlers:
    def __init__(self):
        self.user_sessions = {}  # In-memory cache for speed
        self.content_message_id = {}
        self.menu_message_id = {}
        self.user_languages = {}
        
        # ✅ Rate limiters
        self.general_limiter = RateLimiter(max_requests=10, time_window=60)
        self.deposit_limiter = RateLimiter(max_requests=3, time_window=60)
        self.withdraw_limiter = RateLimiter(max_requests=2, time_window=60)
        self.register_limiter = RateLimiter(max_requests=3, time_window=300)
        self.bingo_limiter = RateLimiter(max_requests=5, time_window=60)
        
        # ✅ Load sessions from database on startup
        self.load_sessions()
        self.load_languages()
    
    
    def load_sessions(self):
        """Load all sessions from database on startup"""
        try:
            all_sessions = db.get_all_sessions()
            for session_data in all_sessions:
                telegram_id = session_data[0]
                session = db.get_session(telegram_id)
                if session and session.get('token'):
                    self.user_sessions[telegram_id] = {
                        'user_id': session.get('user_id'),
                        'token': session.get('token'),
                        'user_data': session.get('user_data', {}),
                        'phone': session.get('phone'),
                        'tg_id': session.get('tg_id')
                    }
            logger.info(f"✅ Loaded {len(self.user_sessions)} sessions from database")
        except Exception as e:
            logger.error(f"❌ Failed to load sessions: {e}")

    def load_languages(self):
        """Load all language preferences from database"""
        try:
            # ✅ Use database module instead of direct SQLite
            all_languages = db.get_all_languages()
            for telegram_id, language in all_languages:
                self.user_languages[telegram_id] = language
            
            logger.info(f"✅ Loaded {len(self.user_languages)} language preferences")
        except Exception as e:
            logger.error(f"❌ Failed to load languages: {e}")

    def save_session_to_db(self, telegram_id):
        """Save current session to database"""
        if telegram_id in self.user_sessions:
            session = self.user_sessions[telegram_id]
            # ✅ Make sure token is included
            if session.get('token'):
                db.save_session(telegram_id, session)
                logger.debug(f"💾 Session saved to database for {telegram_id}")
            else:
                logger.warning(f"⚠️ No token to save for {telegram_id}")

    def save_language_to_db(self, telegram_id):
        """Save language preference to database"""
        if telegram_id in self.user_languages:
            db.save_language(telegram_id, self.user_languages[telegram_id])

    def get_user_language(self, telegram_id):
        """Get user language (with database fallback)"""
        # Check in-memory cache first
        if str(telegram_id) in self.user_languages:
            return self.user_languages.get(str(telegram_id), 'am')
        
        # ✅ Check database
        lang = db.get_language(str(telegram_id))
        self.user_languages[str(telegram_id)] = lang
        return lang

    def set_user_language(self, telegram_id, lang):
        """Set user language (saves to database)"""
        self.user_languages[str(telegram_id)] = lang
        # ✅ Save to database
        db.save_language(str(telegram_id), lang)
        logger.info(f"🌐 Language set to {lang} for {telegram_id}")

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

    # ==================== UPDATE HELPERS ====================

    async def update_content(self, bot, chat_id, message_text, parse_mode='Markdown'):
        """Update content message (the scrollable part)"""
        try:
            if chat_id in self.content_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=self.content_message_id[chat_id],
                        text=message_text,
                        parse_mode=parse_mode
                    )
                    return
                except Exception as e:
                    logger.info(f"Could not edit content, creating new: {e}")
            
            sent = await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=parse_mode
            )
            self.content_message_id[chat_id] = sent.message_id
        except Exception as e:
            logger.error(f"Error updating content: {e}")
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=parse_mode
            )

    async def update_menu(self, bot, chat_id, message_text, keyboard=None, parse_mode='Markdown'):
        """Update menu message (the fixed bottom part)"""
        try:
            if chat_id in self.menu_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=self.menu_message_id[chat_id],
                        text=message_text,
                        parse_mode=parse_mode,
                        reply_markup=keyboard
                    )
                    return
                except Exception as e:
                    logger.info(f"Could not edit menu, creating new: {e}")
                    try:
                        await bot.delete_message(chat_id=chat_id, message_id=self.menu_message_id[chat_id])
                    except:
                        pass
                    self.menu_message_id.pop(chat_id, None)
            
            sent = await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=parse_mode,
                reply_markup=keyboard
            )
            self.menu_message_id[chat_id] = sent.message_id
        except Exception as e:
            logger.error(f"Error updating menu: {e}")
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode=parse_mode,
                reply_markup=keyboard
            )

    def get_main_menu_keyboard(self, telegram_id=None):
        return self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)

    def get_register_keyboard(self, telegram_id=None):
        return self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)

    # ==================== KEYBOARDS ====================

    def get_persistent_reply_keyboard(self, is_auth=True, telegram_id=None):
        """Returns localized reply keyboard based on user's language choice."""
        lang = self.get_user_language(telegram_id) if telegram_id else 'en'
        
        if is_auth:
            if lang == 'am':
                keyboard = [
                    [KeyboardButton("🎮 ቢንጎ ተጫወት")],
                    [
                        KeyboardButton("💰 ገንዘብ አስገባ"),
                        KeyboardButton("💸 ገንዘብ አውጣ"),
                        KeyboardButton("📩 አስተላፍ")
                    ],
                    [
                        KeyboardButton("💰 ቀሪ ሂሳብ"),
                        KeyboardButton("📜 የግብይት ታሪክ"),
                        KeyboardButton("🌐 ቋንቋ")
                    ],
                    [
                        KeyboardButton("🎁 ጋብዝ"),
                        KeyboardButton("ℹ️ መረጃ"),
                        KeyboardButton("📞 አግኙን")
                    ]
                ]
            else:
                keyboard = [
                    [KeyboardButton("🎮 Play Bingo")],
                    [
                        KeyboardButton("💰 Deposit"),
                        KeyboardButton("💸 Withdraw"),
                        KeyboardButton("📩 Transfer")
                    ],
                    [
                        KeyboardButton("💰 Balance"),
                        KeyboardButton("📜 Transactions"),
                        KeyboardButton("🌐 Language")
                    ],
                    [
                        KeyboardButton("🎁 Invite"),
                        KeyboardButton("ℹ️ Info"),
                        KeyboardButton("📞 Contact")
                    ]
                ]
        else:
            if lang == 'am':
                keyboard = [
                    [KeyboardButton("📝 ተመዝገብ")],
                    [KeyboardButton("🌐 Language / ቋንቋ")],
                    [KeyboardButton("📞 አግኙን")]
                ]
            else:
                keyboard = [
                    [KeyboardButton("📝 Register")],
                    [KeyboardButton("🌐 Language / ቋንቋ")],
                    [KeyboardButton("📞 Contact")]
                ]
                
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True
        )

    def get_language_inline_keyboard(self):
        keyboard = [
            [
                InlineKeyboardButton("🇺🇸 English", callback_data='lang_en'),
                InlineKeyboardButton("🇪🇹 አማርኛ (Amharic)", callback_data='lang_am')
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_deposit_keyboard(self):
        keyboard = [
            [
                InlineKeyboardButton("📱 Telebirr", callback_data='deposit_telebirr')
            ],
            [               
                InlineKeyboardButton("🏦 CBE Birr", callback_data='deposit_cbe')
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_withdraw_keyboard(self):
        keyboard = [
            [
                InlineKeyboardButton("📱 Telebirr", callback_data='withdraw_telebirr')
                
            ],
            [
                InlineKeyboardButton("🏦 CBE Birr", callback_data='withdraw_cbe')
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_register_inline_keyboard(self, lang='en'):
        btn_text = "📝 ለመመዝገብ እዚህ ይጫኑ" if lang == 'am' else "📝 Click Here to Register"
        keyboard = [
            [InlineKeyboardButton(btn_text, callback_data='register')]
        ]
        return InlineKeyboardMarkup(keyboard)

    def get_cancel_inline_keyboard(self, lang='en'):
        btn_text = "❌ ሰርዝ" if lang == 'am' else "❌ Cancel Operation"
        keyboard = [
            [InlineKeyboardButton(btn_text, callback_data='cancel')]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    def sanitize_phone(self, phone):
        """Sanitize phone number - keep only digits"""
        return re.sub(r'\D', '', phone)

    def sanitize_amount(self, amount_str):
        """Validate and sanitize amount"""
        try:
            amount = float(amount_str)
            if amount < 0:
                raise ValueError("Amount cannot be negative")
            if amount > 1000000:
                raise ValueError("Amount exceeds maximum limit (1,000,000 ETB)")
            if amount != round(amount, 2):
                raise ValueError("Amount cannot have more than 2 decimal places")
            return round(amount, 2)
        except ValueError as e:
            raise ValueError(f"Invalid amount: {str(e)}")
        
    def generate_secure_password(self, length=12):
        """Generate a cryptographically secure random password"""
        uppercase = string.ascii_uppercase
        lowercase = string.ascii_lowercase
        digits = string.digits
        special = "!@#$%^&*"
        all_chars = uppercase + lowercase + digits + special
        
        password = []
        password.append(secrets.choice(uppercase))
        password.append(secrets.choice(lowercase))
        password.append(secrets.choice(digits))
        password.append(secrets.choice(special))
        
        for _ in range(length - 4):
            password.append(secrets.choice(all_chars))
        
        # Shuffle
        for i in range(len(password) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            password[i], password[j] = password[j], password[i]
        
        return ''.join(password)

    # ==================== LANGUAGE SELECTION ====================

    async def show_language_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        if lang == 'am':
            text = "🌐 *ቋንቋ ይምረጡ / Select Language:*\n\nየአሁኑ ቋንቋ፡ *አማርኛ*"
        else:
            text = "🌐 *Select Language / ቋንቋ ይምረጡ:*\n\nCurrent Language: *English*"

        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=self.get_language_inline_keyboard()
        )

    async def set_language_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query:
            return

        await query.answer()
        chat_id = update.effective_chat.id
        telegram_id = str(query.from_user.id)
        
        selected_lang = query.data.replace('lang_', '')
        self.set_user_language(telegram_id, selected_lang)
        is_auth = self.is_authenticated(telegram_id)

        if selected_lang == 'am':
            message = "✅ ቋንቋው ወደ *አማርኛ* ተቀይሯል።"
        else:
            message = "✅ Language set to *English*."

        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=is_auth, telegram_id=telegram_id)
        )

    # ==================== CHECK & USER ====================

    async def check_user_exists(self, telegram_id):
        """
        CORRECT ORDER:
        1. ALWAYS check backend FIRST (check_user_and_token)
        2. If backend says user exists → handle token status
        3. If backend says user not found → ask to register
        4. Only if backend fails (network) → try database fallback
        """
        
        # ✅ STEP 1: FIRST - Make API call to backend
        # Get tg_id - try from memory first
        tg_id = None
        session = self.user_sessions.get(telegram_id)
        if session and session.get('tg_id'):
            tg_id = session.get('tg_id')
        
        # If not in memory, try database as fallback (only for tg_id)
        if not tg_id:
            db_session = db.get_session(str(telegram_id))
            if db_session and db_session.get('tg_id'):
                tg_id = db_session.get('tg_id')
        
        # If no tg_id anywhere, we can't check backend
        if not tg_id:
            return False, "❌ Please register first with /register."
        
        # Set token for API call (if available in memory)
        if session and session.get('token'):
            api.set_token(session.get('token'))
        
        # ✅ STEP 2: Make API call to backend (ALWAYS FIRST)
        max_retries = 5
        retry_delay = 3
        
        for attempt in range(max_retries):
            logger.info(f"🔍 Checking user {tg_id} with backend (attempt {attempt+1}/{max_retries})...")
            
            response = api.check_user_and_token(tg_id)
            
            # ✅ If API call SUCCEEDED - Backend has the truth!
            if response['success']:
                data = response['data']
                user_data = data.get('user')
                token_status = data.get('token_status')
                new_token = data.get('token')
                
                # ✅ CASE 1: USER EXISTS and token is VALID
                if user_data and token_status == 'valid':
                    logger.info(f"✅ User found and token valid for {telegram_id}")
                    
                    # Update session in memory
                    self.user_sessions[telegram_id] = {
                        'user_id': user_data.get('_id'),
                        'token': session.get('token') if session else None,
                        'user_data': user_data,
                        'phone': user_data.get('phone'),
                        'tg_id': tg_id
                    }
                    self.save_session_to_db(telegram_id)
                    return True, user_data
                
                # ✅ CASE 2: USER EXISTS but token was REFRESHED (new token provided)
                if user_data and token_status == 'refreshed' and new_token:
                    logger.info(f"🔄 Token auto-refreshed for user {telegram_id}")
                    logger.info(f"   New token: {new_token[:20]}...")
                    
                    # Save session with NEW token
                    self.user_sessions[telegram_id] = {
                        'user_id': user_data.get('_id'),
                        'token': new_token,  # NEW TOKEN
                        'user_data': user_data,
                        'phone': user_data.get('phone'),
                        'tg_id': tg_id
                    }
                    api.set_token(new_token)
                    self.save_session_to_db(telegram_id)
                    logger.info(f"✅ Token saved for user {telegram_id}")
                    return True, user_data
                
                # ✅ CASE 3: USER NOT FOUND by backend
                if not user_data:
                    logger.warning(f"❌ User {tg_id} not found in backend")
                    # Delete any local session
                    if telegram_id in self.user_sessions:
                        del self.user_sessions[telegram_id]
                    db.delete_session(telegram_id)
                    api.set_token(None)
                    return False, "❌ Your account was not found. Please register with /register."
                
                # Fallback
                return False, "⚠️ Something went wrong. Please try again."
            
            # ✅ If API call FAILED (network error, timeout, etc.)
            error_msg = response.get('message', '').lower()
            
            # ✅ USER NOT FOUND in backend (API returned error)
            if 'not found' in error_msg or 'user not found' in error_msg:
                logger.warning(f"❌ User {tg_id} not found in backend (API error)")
                if telegram_id in self.user_sessions:
                    del self.user_sessions[telegram_id]
                db.delete_session(telegram_id)
                api.set_token(None)
                return False, "❌ Your account was not found. Please register with /register."
            
            # ✅ NEW: USER ACCOUNT DEACTIVATED → Show message (NO RETRY)
            if 'deactivated' in error_msg or 'account is deactivated' in error_msg:
                logger.warning(f"⚠️ User account is deactivated for {telegram_id}")
                # ✅ Delete session from database and memory
                if telegram_id in self.user_sessions:
                    del self.user_sessions[telegram_id]
                db.delete_session(telegram_id)
                api.set_token(None)
                return False, "❌ Your account has been deactivated. Please contact support."
            
            # ✅ TIMEOUT or NETWORK ERROR → Retry
            if 'timeout' in error_msg or 'timed out' in error_msg or 'connection' in error_msg:
                if attempt < max_retries - 1:
                    logger.warning(f"⏳ Network error (attempt {attempt+1}/{max_retries}), retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"❌ Max retries reached for {telegram_id}")
                    break
            
            # ✅ Any other error - retry
            logger.warning(f"⚠️ Unknown error: {error_msg}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
            break
        
        # ✅ All retries failed → Show server error (NOT registration)
        return False, "⚠️ The server is currently unavailable. Please try again in a few moments."
    
    
    # ==================== START & MENU ====================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with rate limiting, referral handling, and user validation"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        lang = self.get_user_language(telegram_id)
        
        # ✅ Rate limit check - General commands
        is_allowed, remaining = self.general_limiter.is_allowed(telegram_id)
        if not is_allowed:
            msg = "⏳ በጣም ብዙ ጥያቄዎች! እባክዎ 60 ሰከንድ ይጠብቁ." if lang == 'am' else "⏳ Too many requests! Please wait 60 seconds."
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return
        
        # ✅ Validate Telegram user exists
        if not user or not user.id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Invalid user. Please try again."
            )
            return
        
        # ✅ Check for referral code from deep link
        # URL: https://t.me/fetta_bingo_bot?start=ref_6a82f631eaaa9547a17ee472
        if context.args:
            start_param = context.args[0]
            if start_param.startswith('ref_'):
                referral_user_id = start_param.replace('ref_', '')
                # ✅ Validate referral ID format (should be a valid ObjectId or similar)
                if referral_user_id and len(referral_user_id) >= 10:
                    context.user_data['referral_id'] = referral_user_id
                    logger.info(f"🔗 User {telegram_id} came from referral: {referral_user_id}")
                else:
                    logger.warning(f"⚠️ Invalid referral ID format: {referral_user_id}")
        
        # ✅ Check if user is authenticated
        if self.is_authenticated(telegram_id):
            # ✅ Check if user exists in database
            user_exists, result = await self.check_user_exists(telegram_id)
            if not user_exists:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=result,
                    reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                )
                return
            
            user_data = result
            
            # ✅ Validate user data
            if not user_data or not user_data.get('_id'):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Invalid user data. Please register again.",
                    reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                )
                return
            
            # ✅ Build welcome message based on language
            if lang == 'am':
                content = (
                    f"👋 *እንኳን ደህና መጡ, {user_data.get('first_name', user.first_name or 'ተጠቃሚ')}!*\n\n"
                    f"💰 *ቀሪ ሂሳብ:* {self.format_currency(user_data.get('wallet', 0))}\n"
                    f"📱 *ስልክ:* {user_data.get('phone', 'የለም')}\n\n"
                    "ለመቀጠል ከታች ካለው ማውጫ አማራጭ ይምረጡ።"
                )
            else:
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
                reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
            )
        else:
            # ✅ User not authenticated - show registration screen
            if lang == 'am':
                content = (
                    "🎯 *እንኳን ወደ ጋሻ ቢንጎ ቦት በደህና መጡ!*\n\n"
                    "እስካሁን አልተመዘገቡም። እውነተኛ ገንዘብ ማሸነፍ ለመጀመር እባክዎ ይመዝገቡ!\n\n"
                    "✨ *አገልግሎቶች:*\n"
                    "• 🎮 አስደሳች የቢንጎ ጨዋታዎችን ይጫወቱ\n"
                    "• 💰 ገንዘብ ገቢ እና ወጪ ያድርጉ\n"
                    "• 📊 ገቢዎን ይከታተሉ\n"
                    "• 🏆 እውነተኛ ገንዘብ ያሸንፉ"
                )
                reg_text = "👇 ለመመዝገብ ከታች ይጫኑ:"
            else:
                content = (
                    "🎯 *Welcome to Gasha Bingo Bot!*\n\n"
                    "You are currently not registered. Please click Register to start playing and winning real money!\n\n"
                    "✨ *Features:*\n"
                    "• 🎮 Play exciting Bingo games\n"
                    "• 💰 Deposit and withdraw funds\n"
                    "• 📊 Track your earnings\n"
                    "• 🏆 Win real money"
                )
                reg_text = "👇 Tap below to register:"

            # ✅ Send registration screen with persistent keyboard
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                parse_mode='Markdown',
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            
            # ✅ Send registration button
            await context.bot.send_message(
                chat_id=chat_id,
                text=reg_text,
                reply_markup=self.get_register_inline_keyboard(lang=lang)
            )

    # ==================== REGISTER ====================

    async def register_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start registration - Ask user to share phone number with rate limiting"""
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        lang = self.get_user_language(telegram_id)

        # ✅ Rate limit check - Registration attempts (3 per 5 minutes)
        is_allowed, remaining = self.register_limiter.is_allowed(telegram_id)
        if not is_allowed:
            msg = "⏳ በጣም ብዙ የምዝገባ ሙከራዎች! እባክዎ 5 ደቂቃ ይጠብቁ." if lang == 'am' else "⏳ Too many registration attempts! Please wait 5 minutes."
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        # ✅ Validate user exists
        if not user or not user.id:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Invalid user. Please try again.",
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        # ✅ Check if already authenticated
        if self.is_authenticated(telegram_id):
            msg = "✅ ቀደም ብለው ተመዝግበው ገብተዋል!" if lang == 'am' else "✅ You are already registered and logged in!"
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        # ✅ Create keyboard with "Share Phone Number" button
        if lang == 'am':
            phone_btn_text = "📱 የስልክ ቁጥር ያጋሩ"
            cancel_btn_text = "❌ ሰርዝ"
            content = (
                "📝 *ምዝገባ*\n\n"
                "እባክዎን ከታች ያለውን ቁልፍ በመጫን የስልክ ቁጥርዎን ያጋሩ።\n\n"
                "⚠️ *የስልክ ቁጥርዎ ለሚከተሉት ያገለግላል:*\n"
                "• መለያ ማረጋገጫ\n"
                "• ገንዘብ ማውጣት\n"
                "• ደህንነት"
            )
        else:
            phone_btn_text = "📱 Share Phone Number"
            cancel_btn_text = "❌ Cancel"
            content = (
                "📝 *Registration*\n\n"
                "Please share your phone number by tapping the button below.\n\n"
                "⚠️ *Your phone number will be used for:*\n"
                "• Account verification\n"
                "• Withdrawal processing\n"
                "• Security purposes"
            )

        # ✅ Create keyboard with sanitized labels
        keyboard = [
            [KeyboardButton(phone_btn_text, request_contact=True)],
            [InlineKeyboardButton(cancel_btn_text, callback_data='cancel')]
        ]
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return REGISTER_PHONE


    async def register_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle phone number from contact share with validation and secure password generation"""
        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        # ✅ Check if user shared contact or entered manually
        if update.message.contact:
            phone = update.message.contact.phone_number
            # ✅ Sanitize phone number
            phone = self.sanitize_phone(phone)
        else:
            phone = update.message.text.strip()
            # ✅ Sanitize phone number
            phone = self.sanitize_phone(phone)
            
            # ✅ Validate manual entry
            if not re.match(r'^(09|07)\d{8}$', phone) and not re.match(r'^\+251[79]\d{8}$', phone):
                if lang == 'am':
                    content = (
                        "❌ የተሳሳተ የስልክ ቁጥር ቅርጸት።\n\n"
                        "እባክዎን ከታች ያለውን ቁልፍ ተጠቅመው ቁጥርዎን ያጋሩ ወይም በዚሁ ቅርጸት ያስገቡ: 09XXXXXXXX ወይም +2519XXXXXXXX"
                    )
                    phone_btn_text = "📱 የስልክ ቁጥር ያጋሩ"
                    cancel_btn_text = "❌ ሰርዝ"
                else:
                    content = (
                        "❌ Invalid phone number format.\n\n"
                        "Please share your contact using the button below, "
                        "or enter your number in format: 09XXXXXXXX or +2519XXXXXXXX"
                    )
                    phone_btn_text = "📱 Share Phone Number"
                    cancel_btn_text = "❌ Cancel"

                keyboard = [
                    [KeyboardButton(phone_btn_text, request_contact=True)],
                    [InlineKeyboardButton(cancel_btn_text, callback_data='cancel')]
                ]
                reply_markup = ReplyKeyboardMarkup(
                    keyboard,
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    reply_markup=reply_markup
                )
                return REGISTER_PHONE

        # ✅ Format phone number: +2519XXXXXXXX -> 09XXXXXXXX
        if phone.startswith('+251'):
            phone = '0' + phone[4:]
        elif phone.startswith('251'):
            phone = '0' + phone[3:]

        # ✅ Validate Ethiopian phone number format
        if not re.match(r'^(09|07)\d{8}$', phone):
            if lang == 'am':
                content = (
                    "❌ የተሳሳተ የስልክ ቁጥር ቅርጸት።\n\n"
                    "እባክዎ ትክክለኛ የኢትዮጵያ ስልክ ቁጥር መሆኑን ያረጋግጡ።\n"
                    "ቅርጸት: 09XXXXXXXX ወይም +2519XXXXXXXX"
                )
                phone_btn_text = "📱 የስልክ ቁጥር ያጋሩ"
                cancel_btn_text = "❌ ሰርዝ"
            else:
                content = (
                    "❌ Invalid phone number format.\n\n"
                    "Please make sure your number is a valid Ethiopian number.\n"
                    "Format: 09XXXXXXXX or +2519XXXXXXXX"
                )
                phone_btn_text = "📱 Share Phone Number"
                cancel_btn_text = "❌ Cancel"

            keyboard = [
                [KeyboardButton(phone_btn_text, request_contact=True)],
                [InlineKeyboardButton(cancel_btn_text, callback_data='cancel')]
            ]
            reply_markup = ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=True
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=reply_markup
            )
            return REGISTER_PHONE

        # ✅ Store validated phone
        context.user_data['register_phone'] = phone
        
        # ✅ Generate secure password
        generated_password = self.generate_secure_password()
        context.user_data['register_password'] = generated_password

        # ✅ Show loading message
        loading_msg = "⏳ እባክዎ ይጠብቁ... ምዝገባ በሂደት ላይ ነው..." if lang == 'am' else "⏳ Please wait... Registration in progress..."
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=loading_msg
        )

        # ✅ Auto-register - skip password confirmation
        result = await self.register_confirm(update, context)

        # ✅ Delete loading message
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
        except Exception as e:
            logger.warning(f"Could not delete loading message: {e}")

        return result

    async def register_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Complete registration with phone and auto-generated password"""
        # Get chat_id and user
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            chat_id = query.message.chat_id
            user = query.from_user
            telegram_id = str(user.id)
            lang = self.get_user_language(telegram_id)
        else:
            chat_id = update.effective_chat.id
            user = update.effective_user
            telegram_id = str(user.id)
            lang = self.get_user_language(telegram_id)

        phone = context.user_data.get('register_phone')
        password = context.user_data.get('register_password')

        if not phone or not password:
            content = "❌ የምዝገባ ጊዜው አልፎበታል። እባክዎ እንደገና ይጀምሩ: /register" if lang == 'am' else "❌ Registration expired. Please start over with /register"
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            context.user_data.clear()
            return ConversationHandler.END

        # Get Telegram username
        username = user.username
        first_name = user.first_name

        # Format tg_id
        if username:
            tg_id = username.replace('@', '').strip()
            if len(tg_id) < 4:
                tg_id = f"user_{telegram_id}"
            elif len(tg_id) > 31:
                tg_id = tg_id[:31]
        else:
            tg_id = telegram_id

        # ✅ Get referral ID from context
        referral_id = context.user_data.get('referral_id')
        if referral_id:
            logger.info(f"🔗 Registering user with referral: {referral_id}")

        # ✅ FIRST: Try to register user
        response = api.register_user(
            phone=phone, 
            password=password, 
            tg_id=tg_id,
            agent_id=referral_id
        )

        # ✅ CASE 1: Registration SUCCESS - New user
        if response['success']:
            data = response['data']
            token = data.get('token')
            user_data = data.get('user', {})

            if token and user_data:
                logger.info(f"✅ New user registered for {telegram_id}")
                
                # ✅ Save session in memory
                self.user_sessions[telegram_id] = {
                    'user_id': user_data.get('_id'),
                    'token': token,
                    'user_data': user_data,
                    'phone': phone,
                    'tg_id': tg_id
                }
                api.set_token(token)
                
                # ✅ Save session to database
                self.save_session_to_db(telegram_id)
                
                # ✅ Clear cached message IDs
                if hasattr(self, 'menu_message_id') and chat_id in self.menu_message_id:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=self.menu_message_id[chat_id])
                    except:
                        pass
                    self.menu_message_id.pop(chat_id, None)
                
                if hasattr(self, 'content_message_id') and chat_id in self.content_message_id:
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=self.content_message_id[chat_id])
                    except:
                        pass
                    self.content_message_id.pop(chat_id, None)

                wallet_balance = user_data.get('wallet', 0)
                bonus_amount = wallet_balance

                # ✅ Show REGISTRATION SUCCESS message
                if lang == 'am':
                    content = (
                        f"🎉 *ምዝገባዎ በስኬት ተጠናቋል!*\n\n"
                        f"እንኳን ወደ **Gasha Bingo** ደህና መጡ፣ {first_name or 'ተጠቃሚ'}! 👋\n\n"
                        "───────────────\n"
                        "👤 *የተጠቃሚ መረጃ፦*\n"
                        f"📱 **ስልክ ቁጥር:** `{phone}`\n"
                        f"💰 **የአሁኑ ቀሪ ሂሳብ:** {self.format_currency(wallet_balance)}\n"
                        f"🎁 **ቦነስ:** {self.format_currency(bonus_amount)}\n"
                        "───────────────\n\n"
                        "🚀 አሁን መጫወት፣ ገንዘብ ገቢ ማድረግ ወይም ጓደኞችን መጋበዝ ይችላሉ።\n"
                        "የአገልግሎት ማውጫዎ ከታች ተከፍቷል! 👇"
                    )
                else:
                    content = (
                        f"🎉 *Registration Successful!*\n\n"
                        f"Welcome to **Gasha Bingo**, {first_name or 'User'}! 👋\n\n"
                        "───────────────\n"
                        "👤 *Account Overview:*\n"
                        f"📱 **Phone:** `{phone}`\n"
                        f"💰 **Current Balance:** {self.format_currency(wallet_balance)}\n"
                        f"🎁 **Bonus:** {self.format_currency(bonus_amount)}\n"
                        "───────────────\n\n"
                        "🚀 You're all set to play, deposit, or invite friends.\n"
                        "Your main menu options are ready below! 👇"
                    )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    parse_mode='Markdown',
                    reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
                )
                
                # ✅ Clear referral data
                context.user_data.pop('referral_id', None)
                context.user_data.clear()
                return ConversationHandler.END
            else:
                error_msg = response.get('message', 'Registration failed - invalid response')
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ {error_msg}",
                    reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                )
                context.user_data.clear()
                return ConversationHandler.END

        # ✅ CASE 2: Registration FAILED - User might already exist
        error_msg = response.get('message', 'Registration failed').lower()
        
        # ✅ Check if error is "User already exists"
        if 'user already exists' in error_msg or 'already exists' in error_msg:
            logger.info(f"🔄 User already exists with phone {phone}, attempting activation...")
            
            # ✅ Send "Please wait" message
            if lang == 'am':
                waiting_msg = "⏳ እባክዎ ይጠብቁ... መለያዎን እያነቃቃን ነው..."
            else:
                waiting_msg = "⏳ Please wait... Activating your account..."
            
            wait_message = await context.bot.send_message(
                chat_id=chat_id,
                text=waiting_msg
            )
            
            # ✅ Call check_user_and_token to get/refresh token
            check_response = api.check_user_and_token(tg_id)
            
            if check_response['success']:
                data = check_response['data']
                user_data = data.get('user')
                token_status = data.get('token_status')
                new_token = data.get('token')
                
                if user_data:
                    # ✅ Delete waiting message
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=wait_message.message_id)
                    except:
                        pass
                    
                    # ✅ CASE 1: USER EXISTS and token is VALID
                    if token_status == 'valid':
                        logger.info(f"✅ User found and token valid for {telegram_id}")
                        
                        # Get the existing token from session or keep current
                        existing_token = self.user_sessions.get(telegram_id, {}).get('token')
                        token_to_use = existing_token
                        
                        # If no token in memory, try to use the one from check response
                        if not token_to_use:
                            token_to_use = new_token
                        
                        # ✅ Save session in memory
                        self.user_sessions[telegram_id] = {
                            'user_id': user_data.get('_id'),
                            'token': token_to_use,
                            'user_data': user_data,
                            'phone': user_data.get('phone'),
                            'tg_id': tg_id
                        }
                        
                        # ✅ Save to database
                        self.save_session_to_db(telegram_id)
                        
                        # ✅ Set token for API
                        if token_to_use:
                            api.set_token(token_to_use)
                        
                        logger.info(f"✅ Session saved for user {telegram_id}")
                    
                    # ✅ CASE 2: USER EXISTS but token was REFRESHED (new token provided)
                    elif token_status == 'refreshed' and new_token:
                        logger.info(f"🔄 Token auto-refreshed for user {telegram_id}")
                        logger.info(f"   New token: {new_token[:20]}...")
                        
                        # ✅ Save session with NEW token in memory
                        self.user_sessions[telegram_id] = {
                            'user_id': user_data.get('_id'),
                            'token': new_token,  # NEW TOKEN
                            'user_data': user_data,
                            'phone': user_data.get('phone'),
                            'tg_id': tg_id
                        }
                        
                        # ✅ Update API client with new token
                        api.set_token(new_token)
                        
                        # ✅ Save session to database
                        self.save_session_to_db(telegram_id)
                        
                        logger.info(f"✅ Token saved for user {telegram_id}")
                    
                    # ✅ CASE 3: Fallback - Try to login
                    else:
                        logger.info(f"🔄 No token provided, attempting login for {telegram_id}")
                        login_response = api._make_request('POST', '/auth/login', {
                            'phone': phone,
                            'password': password
                        })
                        
                        if login_response['success']:
                            login_data = login_response['data']
                            token_to_use = login_data.get('token')
                            user_info = login_data.get('user', {})
                            
                            if token_to_use:
                                # ✅ Save session with login token
                                self.user_sessions[telegram_id] = {
                                    'user_id': user_info.get('_id') or user_data.get('_id'),
                                    'token': token_to_use,
                                    'user_data': user_info or user_data,
                                    'phone': phone,
                                    'tg_id': tg_id
                                }
                                api.set_token(token_to_use)
                                self.save_session_to_db(telegram_id)
                                logger.info(f"✅ Login successful for user {telegram_id}")
                            else:
                                logger.error(f"❌ Login failed - no token received")
                                # Show error and return
                                content = "❌ መለያዎን ማነቃቃት አልተቻለም። እባክዎ በኋላ እንደገና ይሞክሩ።" if lang == 'am' else "❌ Could not activate your account. Please try again later."
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=content,
                                    reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                                )
                                context.user_data.clear()
                                return ConversationHandler.END
                        else:
                            logger.error(f"❌ Login failed: {login_response.get('message')}")
                            content = "❌ መለያዎን ማነቃቃት አልተቻለም። እባክዎ በኋላ እንደገና ይሞክሩ።" if lang == 'am' else "❌ Could not activate your account. Please try again later."
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=content,
                                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                            )
                            context.user_data.clear()
                            return ConversationHandler.END
                    
                    # ✅ Clear cached message IDs
                    if hasattr(self, 'menu_message_id') and chat_id in self.menu_message_id:
                        try:
                            await context.bot.delete_message(chat_id=chat_id, message_id=self.menu_message_id[chat_id])
                        except:
                            pass
                        self.menu_message_id.pop(chat_id, None)
                    
                    if hasattr(self, 'content_message_id') and chat_id in self.content_message_id:
                        try:
                            await context.bot.delete_message(chat_id=chat_id, message_id=self.content_message_id[chat_id])
                        except:
                            pass
                        self.content_message_id.pop(chat_id, None)

                    # ✅ Get the saved user data
                    saved_user_data = self.user_sessions[telegram_id]['user_data']
                    wallet_balance = saved_user_data.get('wallet', 0)
                    bonus_amount = wallet_balance

                    # ✅ Show ACTIVATION SUCCESS message (different from registration)
                    if lang == 'am':
                        content = (
                            f"🎉 *አክቲቪኑ በስኬት ተጠናቋል!*\n\n"
                            f"እንኳን ወደ **Gasha Bingo** ተመለሱ፣ {first_name or 'ተጠቃሚ'}! 👋\n\n"
                            "───────────────\n"
                            "👤 *የተጠቃሚ መረጃ፦*\n"
                            f"📱 **ስልክ ቁጥር:** `{phone}`\n"
                            f"💰 **የአሁኑ ቀሪ ሂሳብ:** {self.format_currency(wallet_balance)}\n"
                            f"🎁 **ቦነስ:** {self.format_currency(bonus_amount)}\n"
                            "───────────────\n\n"
                            "🚀 አሁን መጫወት፣ ገንዘብ ገቢ ማድረግ ወይም ጓደኞችን መጋበዝ ይችላሉ።\n"
                            "የአገልግሎት ማውጫዎ ከታች ተከፍቷል! 👇"
                        )
                    else:
                        content = (
                            f"🎉 *Activation Successful!*\n\n"
                            f"Welcome back to **Gasha Bingo**, {first_name or 'User'}! 👋\n\n"
                            "───────────────\n"
                            "👤 *Account Overview:*\n"
                            f"📱 **Phone:** `{phone}`\n"
                            f"💰 **Current Balance:** {self.format_currency(wallet_balance)}\n"
                            f"🎁 **Bonus:** {self.format_currency(bonus_amount)}\n"
                            "───────────────\n\n"
                            "🚀 You're all set to play, deposit, or invite friends.\n"
                            "Your main menu options are ready below! 👇"
                        )

                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=content,
                        parse_mode='Markdown',
                        reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
                    )
                    
                    # ✅ Clear referral data
                    context.user_data.pop('referral_id', None)
                    context.user_data.clear()
                    return ConversationHandler.END
                    
                else:
                    # No user data from check_user_and_token
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=wait_message.message_id)
                    except:
                        pass
                    
                    content = "❌ የተጠቃሚ መረጃ አልተገኘም።" if lang == 'am' else "❌ User data not found."
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=content,
                        reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                    )
                    context.user_data.clear()
                    return ConversationHandler.END
            else:
                # check_user_and_token failed
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=wait_message.message_id)
                except:
                    pass
                
                content = f"❌ {check_response.get('message', 'Activation failed')}"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=content,
                    reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
                )
                context.user_data.clear()
                return ConversationHandler.END
        
        # ✅ CASE 3: Other error (not user exists)
        else:
            content = f"❌ {response.get('message', 'Registration failed')}"
            await context.bot.send_message(
                chat_id=chat_id,
                text=content,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            context.user_data.clear()
            return ConversationHandler.END

    # ==================== PLAY BINGO ====================


    async def play_bingo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Play Bingo - Open as Telegram WebApp with code in URL"""
        
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)

        # ✅ Rate limit check - Bingo games (5 per minute)
        is_allowed, remaining = self.bingo_limiter.is_allowed(telegram_id)
        if not is_allowed:
            lang = self.get_user_language(telegram_id)
            msg = "⏳ በጣም ብዙ የጨዋታ ጥያቄዎች! እባክዎ 60 ሰከንድ ይጠብቁ." if lang == 'am' else "⏳ Too many game requests! Please wait 60 seconds."
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=self.get_persistent_reply_keyboard(
                    is_auth=True,
                    telegram_id=telegram_id
                )
            )
            return

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)

        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(
                    is_auth=False,
                    telegram_id=telegram_id
                )
            )
            return

        user_data = result

        self.user_sessions[telegram_id]['user_data'] = user_data

        user_id = self.user_sessions[telegram_id].get('user_id')

        # Generate one-time game code
        code_response = api.generate_game_code(user_id)

        if not code_response['success']:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Failed to generate game link. Please try again.",
                reply_markup=self.get_persistent_reply_keyboard(
                    is_auth=True,
                    telegram_id=telegram_id
                )
            )
            return

        code = code_response['data']['code']

        from telegram import WebAppInfo

        # Bingo WebApp URL
        bingo_url = (
            f"https://addis-bingo-game-client.vercel.app"
            f"/user/lobby?code={code}"
        )

        lang = self.get_user_language(telegram_id)
        first_name = user.first_name or "User"

        if lang == 'am':
            welcome_text = (
                f"🎉 *እንኳን ደህና መጡ {first_name}!*\n\n"
                "🎮 ጨዋታውን ለመጀመር ከታች ያለውን ቁልፍ ይጫኑ👇"
            )
            button_label = "🎮 ቢንጎ ይጫወቱ"
        else:
            welcome_text = (
                f"🎉 *Welcome, {first_name}!*\n\n"
                "🎮 Click the button below to start playing👇"
            )
            button_label = "🎮 Play Bingo"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    button_label,
                    web_app=WebAppInfo(url=bingo_url)
                )
            ]
        ])

        # Send temporary message
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        
        # Schedule deletion after 20 seconds
        context.job_queue.run_once(
            self.delete_bingo_message,
            20,
            data={
                'chat_id': chat_id,
                'message_id': message.message_id
            }
        )

        
    async def delete_bingo_message(self, context: ContextTypes.DEFAULT_TYPE):
        """Delete temporary Bingo WebApp message after 1 minute."""

        job_data = context.job.data

        chat_id = job_data['chat_id']
        message_id = job_data['message_id']

        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id
            )

            print(
                f"🗑️ Deleted Bingo launch message "
                f"{message_id} from chat {chat_id}"
            )

        except Exception as e:
            print(
                f"⚠️ Could not delete Bingo launch message "
                f"{message_id}: {e}"
            )

    # ==================== DEPOSIT ====================

    async def deposit_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start deposit process with rate limiting"""
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        lang = self.get_user_language(telegram_id)

        # ✅ Rate limit check - Deposit requests (3 per minute)
        is_allowed, remaining = self.deposit_limiter.is_allowed(telegram_id)
        if not is_allowed:
            msg = "⏳ በጣም ብዙ የገቢ ጥያቄዎች! እባክዎ 60 ሰከንድ ይጠብቁ." if lang == 'am' else "⏳ Too many deposit requests! Please wait 60 seconds."
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)
        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        if lang == 'am':
            content = (
                "💰 *ገንዘብ ማስገቢያ*\n\n"
                "• አነስተኛ ገቢ: 10 ETB\n"
                "• ቦነስ: ከ 50 ETB በላይ 10% ተጨማሪ ቦነስ\n\n"
                "የከፍያ አይነት ይምረጡ 👇👇👇👇👇"
            )
        else:
            content = (
                "💰 *Deposit Funds*\n\n"
                "• Minimum deposit: 10 ETB\n"
                "• Bonus: Have for deposits above 50 ETB\n\n"
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
        lang = self.get_user_language(telegram_id)

        method_names = {
            'telebirr': '📱 Telebirr',
            'cbe': '🏦 CBE Birr',
            'awash': '🏛️ Awash Bank',
            'cbe_bank': '💳 Commercial Bank of Ethiopia (CBE)'
        }
        method_display = method_names.get(method, method.upper())

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_accountants(blocked=False)

        if not response['success'] or not response['data']:
            err_msg = "❌ የክፍያ ዝርዝሮች በአሁኑ ጊዜ አይገኙም። እባክዎ በኋላ እንደገና ይሞክሩ።" if lang == 'am' else "❌ No deposit payment details currently available. Please try again later."
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg
            )
            return ConversationHandler.END

        accountants = response['data']
        accountant = next((acc for acc in accountants if method in acc.get('bankName', '').lower()), accountants[0])
        context.user_data['deposit_accountant'] = accountant

        phone_or_acc = accountant.get('phoneNumber') or accountant.get('accountNumber') or 'N/A'
        account_name = accountant.get('fullName', 'N/A')

        if lang == 'am':
            if method in ['telebirr', 'cbe']:
                details = f"📱 *ስልክ ቁጥር:* `{phone_or_acc}`"
            else:
                details = f"🏦 *የባንክ ሂሳብ:* `{phone_or_acc}`\n👤 *ስም:* {account_name}"

            content = (
                f"💰 *በ {method_display} ገንዘብ ማስገቢያ*\n\n"
                f"{details}\n\n"
                f"እባክዎን ማስገባት የሚፈልጉትን የገንዘብ መጠን ያስገቡ (አነስተኛ: 10 ብር):"
            )
        else:
            if method in ['telebirr', 'cbe']:
                details = f"📱 *Phone:* `{phone_or_acc}`"
            else:
                details = f"🏦 *Account:* `{phone_or_acc}`\n👤 *Name:* {account_name}"

            content = (
                f"💰 *Deposit via {method_display}*\n\n"
                f"{details}\n\n"
                f"Please enter the amount you want to deposit (min: 10 ETB):"
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard(lang=lang)
        )
        return DEPOSIT_AMOUNT

    async def deposit_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle deposit amount input with sanitization"""
        if not update.message:
            return DEPOSIT_AMOUNT

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        # ✅ Sanitize and validate amount
        try:
            amount = self.sanitize_amount(update.message.text.strip())
        except ValueError as e:
            err_msg = f"❌ {str(e)}" if lang == 'am' else f"❌ {str(e)}"
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return DEPOSIT_AMOUNT

        # ✅ Validate minimum deposit
        if amount < 10:
            err_msg = "❌ አነስተኛ ገቢ 10 ብር ነው።" if lang == 'am' else "❌ Minimum deposit is 10 ETB."
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return DEPOSIT_AMOUNT

        # ✅ Store validated amount
        context.user_data['deposit_amount'] = amount
        
        # ✅ Calculate bonus
        bonus = amount * 0.005 if amount > 50 else 0
        total = amount + bonus

        # ✅ Get method and accountant info
        method = context.user_data.get('deposit_method', 'telebirr')
        accountant = context.user_data.get('deposit_accountant', {})

        method_names = {
            'telebirr': '📱 Telebirr',
            'cbe': '🏦 CBE Birr',
            'awash': '🏛️ Awash Bank',
            'cbe_bank': '💳 Commercial Bank of Ethiopia (CBE)'
        }
        method_display = method_names.get(method, method.upper())

        phone_or_acc = accountant.get('phoneNumber') or accountant.get('accountNumber') or 'N/A'
        account_name = accountant.get('fullName', '')

        # ✅ Build response based on language
        if lang == 'am':
            if method in ['telebirr', 'cbe']:
                account_info = f"📱 *{method_display}*\n\n`{phone_or_acc}`"
            else:
                account_info = f"{method_display}\n\n🏦 *አካውንት:* `{phone_or_acc}`\n👤 *ስም:* {account_name}"

            instruction = (
                f"1. ከላይ ባለው የ {method_display} አካውንት {self.format_currency(amount)} ያስገቡ\n"
                f"2. የከፈላችሁበትን የግብይት መረጃ የያዘ አጭር መልእክት (SMS) ከ {method_display} ይደርስዎታል\n"
                f"3. ያገኙትን SMS በሙሉ ኮፒ በማድረግ እዚህ በታች ያለው ቴሌግራም መልእክት ቦታ ውስጥ ፔስት በማድረግ ይላኩት"
            )

            content = (
                f"✅ *መጠን:* {self.format_currency(amount)}\n"
                f"🎁 *ቦነስ:* {self.format_currency(bonus)}\n"
                f"💰 *ጠቅላላ የሚገባ:* {self.format_currency(total)}\n\n"
                f"───────────────\n"
                f"{account_info}\n\n"
                f"*{method_display} መመሪያ፦*\n"
                f"{instruction}\n\n"
                f"እባክዎ የትራንዛክሽን መለያ ቁጥር (Transaction ID / Ref) ያስገቡ:"
            )
        else:
            if method in ['telebirr', 'cbe']:
                account_info = f"📱 *{method_display}*\n\n`{phone_or_acc}`"
            else:
                account_info = f"{method_display}\n\n🏦 *Account:* `{phone_or_acc}`\n👤 *Name:* {account_name}"

            instruction = (
                f"1. Transfer {self.format_currency(amount)} to the {method_display} account above.\n"
                f"2. You will receive a confirmation SMS containing transaction details.\n"
                f"3. Copy the entire SMS or paste it into the message box below."
            )

            content = (
                f"✅ *Amount:* {self.format_currency(amount)}\n"
                f"🎁 *Bonus:* {self.format_currency(bonus)}\n"
                f"💰 *Total Credit:* {self.format_currency(total)}\n\n"
                f"───────────────\n"
                f"{account_info}\n\n"
                f"*{method_display} Instructions:*\n"
                f"{instruction}\n\n"
                f"Please enter your transaction reference / ID:"
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard(lang=lang)
        )
        return DEPOSIT_VERIFICATION

    async def deposit_verify(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return DEPOSIT_VERIFICATION

        transaction_id = update.message.text.strip()
        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        if not transaction_id:
            err_msg = "❌ እባክዎ ትክክለኛ የትራንዛክሽን መለያ ያስገቡ:" if lang == 'am' else "❌ Please enter a valid transaction ID:"
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return DEPOSIT_VERIFICATION

        amount = context.user_data.get('deposit_amount')
        accountant = context.user_data.get('deposit_accountant')
        method = context.user_data.get('deposit_method')
        user_data = self.user_sessions[telegram_id]['user_data']

        bonus = amount * 0.005 if amount > 50 else 0
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
            if lang == 'am':
                content = (
                    f"✅ *የገቢ ጥያቄዎ ተልኳል!*\n\n"
                    f"💰 መጠን: {self.format_currency(amount)}\n"
                    f"🎁 ቦነስ: {self.format_currency(bonus)}\n"
                    f"💰 ጠቅላላ: {self.format_currency(total)}\n"
                    f"📱 መንገድ: {method.upper()}\n\n"
                    f"⏳ ከተረጋገጠ በኋላ ገቢ ይደረጋል።"
                )
            else:
                content = (
                    f"✅ *Deposit submitted!*\n\n"
                    f"💰 Amount: {self.format_currency(amount)}\n"
                    f"🎁 Bonus: {self.format_currency(bonus)}\n"
                    f"💰 Total: {self.format_currency(total)}\n"
                    f"📱 Method: {method.upper()}\n\n"
                    f"⏳ Your deposit will be credited after manual review."
                )
        else:
            content = f"❌ የገቢ ጥያቄ አልተሳካም: {response.get('message', 'Unknown error')}" if lang == 'am' else f"❌ Deposit submission failed: {response.get('message', 'Unknown error')}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
        )
        context.user_data.clear()
        return ConversationHandler.END

    # ==================== WITHDRAW ====================

    async def withdraw_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start withdrawal process with rate limiting"""
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        lang = self.get_user_language(telegram_id)

        # ✅ Rate limit check - Withdrawal requests (2 per minute)
        is_allowed, remaining = self.withdraw_limiter.is_allowed(telegram_id)
        if not is_allowed:
            msg = "⏳ በጣም ብዙ የወጪ ጥያቄዎች! እባክዎ 60 ሰከንድ ይጠብቁ." if lang == 'am' else "⏳ Too many withdrawal requests! Please wait 60 seconds."
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)
        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return ConversationHandler.END

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_user_profile()

        if response['success']:
            user_data = response['data']
            self.user_sessions[telegram_id]['user_data'] = user_data
        else:
            user_data = self.get_user_data(telegram_id)

        if lang == 'am':
            content = (
                f"💳 *ገንዘብ ማውጫ*\n\n"
                f"💰 *ያለዎት ቀሪ ሂሳብ:* {self.format_currency(user_data.get('wallet', 0))}\n"
                f"💳 *አነስተኛ ወጪ:* {self.format_currency(100)}\n\n"
                f"ከታች ያለውን የመቀበያ መንገድ ይምረጡ:"
            )
        else:
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
        telegram_id = str(query.from_user.id)
        lang = self.get_user_language(telegram_id)

        method_names = {
            'telebirr': '📱 Telebirr',
            'cbe': '🏦 CBE Birr',
            'awash': '🏛️ Awash Bank',
            'cbe_bank': '💳 CBE'
        }
        method_display = method_names.get(method, method.upper())

        content = f"💳 *በ {method_display} ገንዘብ ማውጫ*\n\nእባክዎ ማውጣት የሚፈልጉትን የገንዘብ መጠን ያስገቡ (አነስተኛ: 100 ETB):" if lang == 'am' else f"💳 *Withdraw via {method_display}*\n\nPlease enter the amount you wish to withdraw (min: 100 ETB):"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard(lang=lang)
        )
        return WITHDRAW_AMOUNT

    async def withdraw_amount(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle withdrawal amount input with sanitization"""
        if not update.message:
            return WITHDRAW_AMOUNT

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        # ✅ Sanitize and validate amount
        try:
            amount = self.sanitize_amount(update.message.text.strip())
        except ValueError as e:
            err_msg = f"❌ {str(e)}" if lang == 'am' else f"❌ {str(e)}"
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return WITHDRAW_AMOUNT

        # ✅ Validate minimum withdrawal
        if amount < 100:
            err_msg = "❌ አነስተኛ የማውጫ መጠን 100 ብር ነው።" if lang == 'am' else "❌ Minimum withdrawal amount is 100 ETB."
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return WITHDRAW_AMOUNT

        # ✅ Get user balance
        user_data = self.user_sessions[telegram_id]['user_data']
        balance = user_data.get('wallet', 0)

        # ✅ Validate sufficient balance
        if amount > balance:
            err_msg = f"❌ በቂ ቀሪ ሂሳብ የሎትም። ያለው ቀሪ ሂሳብ {self.format_currency(balance)} ነው።" if lang == 'am' else f"❌ Insufficient balance. Available balance is {self.format_currency(balance)}."
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return WITHDRAW_AMOUNT

        # ✅ Store validated amount
        context.user_data['withdraw_amount'] = amount

        content = f"💳 *መጠን:* {self.format_currency(amount)}\n\nእባክዎ ገንዘቡ የሚገባበትን የሂሳብ/ስልክ ቁጥር ያስገቡ:" if lang == 'am' else f"💳 *Amount:* {self.format_currency(amount)}\n\nPlease enter your account/phone number for withdrawal:"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_cancel_inline_keyboard(lang=lang)
        )
        return WITHDRAW_ACCOUNT

    async def withdraw_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return WITHDRAW_ACCOUNT

        account = update.message.text.strip()
        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        if not account:
            err_msg = "❌ የተሳሳተ ሂሳብ ቁጥር። እባክዎ እንደገና ያስገቡ:" if lang == 'am' else "❌ Invalid account. Please enter your account number:"
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return WITHDRAW_ACCOUNT

        context.user_data['withdraw_account'] = account
        content = "የባንክ ሂሳቡ ባለቤት ሙሉ ስም ያስገቡ:" if lang == 'am' else "Enter full account holder name:"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=self.get_cancel_inline_keyboard(lang=lang)
        )
        return WITHDRAW_NAME

    async def withdraw_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message:
            return WITHDRAW_NAME

        name = update.message.text.strip()
        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        if not name:
            err_msg = "❌ እባክዎ ትክክለኛ የባለቤት ስም ያስገቡ:" if lang == 'am' else "❌ Please enter a valid account holder name:"
            await context.bot.send_message(
                chat_id=chat_id,
                text=err_msg,
                reply_markup=self.get_cancel_inline_keyboard(lang=lang)
            )
            return WITHDRAW_NAME

        amount = context.user_data.get('withdraw_amount')
        method = context.user_data.get('withdraw_method')
        account = context.user_data.get('withdraw_account')
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
            if lang == 'am':
                content = (
                    f"✅ *የወጪ ጥያቄዎ ተልኳል!*\n\n"
                    f"💰 መጠን: {self.format_currency(amount)}\n"
                    f"📱 መንገድ: {method.upper()}\n"
                    f"📱 ሂሳብ/ስልክ: {account}\n"
                    f"👤 ስም: {name}\n\n"
                    f"⏳ ከተረጋገጠ በኋላ ገቢ ይደረጋል።"
                )
            else:
                content = (
                    f"✅ *Withdrawal request submitted!*\n\n"
                    f"💰 Amount: {self.format_currency(amount)}\n"
                    f"📱 Method: {method.upper()}\n"
                    f"📱 Account: {account}\n"
                    f"👤 Name: {name}\n\n"
                    f"⏳ Processed following manual verification."
                )
        else:
            content = f"❌ የገንዘብ ወጪ ጥያቄ አልተሳካም: {response.get('message', 'Unknown error')}" if lang == 'am' else f"❌ Withdrawal failed: {response.get('message', 'Unknown error')}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
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
        lang = self.get_user_language(telegram_id)

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)
        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return

        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_user_profile()

        if response['success']:
            user_data = response['data']
            self.user_sessions[telegram_id]['user_data'] = user_data

            if lang == 'am':
                content = (
                    f"📊 *የእርስዎ ሂሳብ*\n\n"
                    f"💰 *ቀሪ ሂሳብ:* {self.format_currency(user_data.get('wallet', 0))}\n"
                    f"📈 *የዛሬ ገቢ:* {self.format_currency(user_data.get('dailyEarnings', 0))}\n"
                    f"📊 *የሳምንት ገቢ:* {self.format_currency(user_data.get('weeklyEarnings', 0))}\n"
                    f"🏆 *አጠቃላይ ገቢ:* {self.format_currency(user_data.get('totalEarnings', 0))}\n\n"
                    f"💳 አነስተኛ ወጪ፡ {self.format_currency(100)}\n"
                    f"💵 ከፍተኛ ገቢ፡ {self.format_currency(10000)}"
                )
            else:
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
            content = f"❌ ቀሪ ሂሳብ ማግኘት አልተቻለም: {response['message']}" if lang == 'am' else f"❌ Failed to fetch balance: {response['message']}"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
        )

    # ==================== HISTORY ====================

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        lang = self.get_user_language(telegram_id)

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)
        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return

        user_data = self.user_sessions[telegram_id]['user_data']
        api.set_token(self.user_sessions[telegram_id]['token'])
        response = api.get_transactions(user_data.get('_id'), limit=10)

        if not response['success']:
            content = f"❌ የግብይት ታሪክ ማግኘት አልተቻለም: {response['message']}" if lang == 'am' else f"❌ Failed to fetch transactions: {response['message']}"
        else:
            transactions = response['data']
            if not transactions:
                content = "📝 ምንም የግብይት ታሪክ የለም።" if lang == 'am' else "📝 No transactions found."
            else:
                content = "📝 *የግብይት ታሪክ*\n\n" if lang == 'am' else "📝 *Transaction History*\n\n"
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
            reply_markup=self.get_persistent_reply_keyboard(is_auth=True, telegram_id=telegram_id)
        )

    # ==================== INFO ====================

    async def show_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        SUPPORT_LINK = "https://t.me/+G6sILM_Sur0yYzZk"
        CHANNEL_LINK = "https://t.me/gasha_bingo"

        if lang == 'am':
            content = (
                "🎮 *Gasha Bingo — አጠቃቀም እና የጨዋታ ህጎች*\n\n"
                "🌐 *ቋንቋ ለመቀየር (Change Language):*\n"
                "• የቋንቋ ምርጫዎን ለመቀየር ከታች ባለው ሜኑ ላይ **'Language/ቋንቋ 🌐'** የሚለውን ቁልፍ ይጫኑ።\n\n"
                "───────────────\n"
                "1️⃣ *እንዴት መመዝገብ ይቻላል? (Registration)*\n"
                "1. **'Register / መመዝገብ'** የሚለውን ቁልፍ ይጫኑ።\n"
                "2. **'Share Phone Number / ስልክ ቁጥር ያጋሩ'** የሚለው ሲመጣ ይንኩት።\n"
                "3. በትክክል መመዝገብዎን የሚያረጋግጥ መልእክት ይደርስዎታል![cite: 1]\n\n"

                "2️⃣ *እንዴት ገንዘብ ገቢ ማድረግ ይቻላል? (Deposit)*\n"
                "1. **'Deposit / ገቢ ማድረግ'** የሚለውን ቁልፍ ይንኩ።\n"
                "2. የሚያስተላልፉትን የገንዘብ መጠን ያስገቡ (አነስተኛ ገቢ: 10 ETB / ከ 50 ETB በላይ ቦነስ አለው)።\n"
                "3. የክፍያ አይነት ይምረጡ (Telebirr ወይም CBE)።\n"
                "4. በተያያዘው ስልክ ወይም አካውንት ገንዘቡን አስተላልፈው የሚደርስዎትን የግብይት ቁጥር (Transaction ID) ያስገቡ።\n\n"

                "3️⃣ *እንዴት መጫወት ይቻላል? (How to Play)*\n"
                "1. **'Play Bingo'** የሚለውን ተጭነው የጨዋታ ዝርዝሮች ይመጣሉ ከነሱ የሚፈልጉትን play በማለት ከ1-400 ካሉት የመጫወቻ ካርዶች አንዱን ይምረጡ (በቀይ የተከበቡት በሌላ ተጫዋች የተያዙ ናቸው)።\n"
                "2. የምዝገባ ሰከንድ አልቆ ጨዋታው ሲጀምር ከ1 እስከ 75 ያሉት ቁጥሮች በዘነደ መጥራት ይጀምራሉ።\n"
                "3. የሚጠራው ቁጥር የእርስዎ ካርድ ላይ ካለ ቁጥሩን **ክሊክ** በማድረግ ይምረጡት (ከተሳሳቱ ድጋሚ ተጭነው ማጥፋት ይችላሉ)።\n"
                "4. የተጠሩት ቁጥሮች **ወደጎን**፣ **ወደታች**፣ **በአግዳሚ (X)** ወይም **አራቱን ማእዘናት** ሲሞሉልዎት ወዲያውኑ **'BINGO'** የሚለውን ተጭነው ያሸንፉ! *(⚠️ ሳይሞላ BINGO ካሉ ከጨዋታው ይታገዳሉ)*\n\n"

                "4️⃣ *እንዴት ገንዘብ ወጪ ማድረግ ይቻላል? (Withdrawal)*\n"
                "1. **'Withdraw / ወጪ ማድረግ'** የሚለውን ቁልፍ ይንኩ።\n"
                "2. ማውጣት የሚፈልጉትን የገንዘብ መጠን ያስገቡ።\n"
                "3. ገንዘቡ ገቢ የሚሆንበትን የቴሌብር ወይም የባንክ ሂሳብ ቁጥርዎን ያስገቡ።\n"
                "4. ጥያቄዎ ተቀባይነት አግኝቶ ገንዘቡ በደቂቃዎች ውስጥ ይላክልዎታል![cite: 1]\n\n"

                "───────────────\n"
                "💬 *ለበለጠ መረጃ እና ለማንኛውም ችግር:*\n"
                f"📢 **ቻናል:** [Gasha Bingo Channel]({CHANNEL_LINK})\n"
                f"🛠 **እርዳታ ለማግኘት:** [Customer Support]({SUPPORT_LINK})"
            )
        else:
            content = (
                "🎮 *Gasha Bingo — Usage & Game Rules*\n\n"
                "🌐 *How to Change Language:*\n"
                "• To change your language preference, click the **'Change Language 🌐'** button in the main menu.\n\n"
                "───────────────\n"
                "1️⃣ *How to Register:*\n"
                "1. Click the **'Register'** button.\n"
                "2. Tap **'Share Phone Number'** when prompted.\n"
                "3. You will receive a confirmation message once registered successfully![cite: 1]\n\n"

                "2️⃣ *How to Deposit Funds:*\n"
                "1. Click the **'Deposit'** button.\n"
                "2. Enter the amount you wish to transfer (Minimum: 10 ETB / 10% Bonus for deposits > 50 ETB).\n"
                "3. Choose your payment method (Telebirr or CBE).\n"
                "4. Transfer the money to the provided details and enter the received Transaction ID.\n\n"

                "3️⃣ *How to Play Bingo:*\n"
                "1. Click **'Play Bingo'** and Select prefered game and select a card from 1-400 (Red highlighted cards are already taken).\n"
                "2. Once the countdown ends, numbers from 1 to 75 will be called randomly.\n"
                "3. If a called number matches your card, **click** to mark it (click again to unmark if misclicked).\n"
                "4. Complete a **horizontal line**, **vertical line**, **diagonal (X)**, or **4 corners**, then hit **'BINGO'** to win! *(⚠️ False Bingo calls lead to disqualification)*\n\n"

                "4️⃣ *How to Withdraw Winnings:*\n"
                "1. Click the **'Withdraw'** button.\n"
                "2. Enter the amount you wish to withdraw.\n"
                "3. Provide your Telebirr number or bank account details.\n"
                "4. Your request will be processed, and funds transferred within minutes![cite: 1]\n\n"

                "───────────────\n"
                "💬 *Need Help or Support?*\n"
                f"📢 **Official Channel:** [Gasha Bingo Channel]({CHANNEL_LINK})\n"
                f"🛠 **Customer Support:** [Support Team]({SUPPORT_LINK})"
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=self.get_persistent_reply_keyboard(is_auth=self.is_authenticated(telegram_id), telegram_id=telegram_id)
        )

    # ==================== INVITE ====================

    async def show_invite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        is_auth = self.is_authenticated(telegram_id)
        lang = self.get_user_language(telegram_id)

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)
        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return

        user_id = self.user_sessions.get(telegram_id, {}).get('user_id', '')
        bot_username = "gasha_bingo_bot"
        invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}" if user_id else f"https://t.me/{bot_username}"

        if lang == 'am':
            content = (
                "🎁 *ጓደኞችን ይጋብዙ — ኮሚሽን ያግኙ!*\n\n"
                "የመጋበዣ ሊንክዎን ለጓደኞችዎ በማጋራት እና ሲመዘገቡ ተጨማሪ ገቢ ያግኙ!\n\n"
                "───────────────\n"
                "✨ *እንዴት ይሰራል?*\n"
                "1️⃣ ከታች ያለውን የመጋበዣ ሊንክ ኮፒ ያድርጉ\n"
                "2️⃣ ለጓደኞችዎ ወይም በሶሻል ሚዲያ ያጋሩ\n"
                "3️⃣ ጓደኞችዎ በሊንክዎ ሲመዘገቡ እና ሲጫወቱ ቦነስ ያግኙ!\n\n"
                "🔗 *የእርስዎ ልዩ የመጋበዣ ሊንክ፦*\n"
                f"`{invite_link}`\n\n"
                "👆 *ሊንኩን ተጭነው በመያዝ ኮፒ ማድረግ ይችላሉ።*"
            )
        else:
            content = (
                "🎁 *Invite Friends — Earn Rewards!*\n\n"
                "Share your personal referral link with friends and start earning bonuses!\n\n"
                "───────────────\n"
                "✨ *How It Works:*\n"
                "1️⃣ Copy your unique invite link below.\n"
                "2️⃣ Share it with friends or on social media.\n"
                "3️⃣ Earn commission whenever your friends register and play!\n\n"
                "🔗 *Your Personal Referral Link:*\n"
                f"`{invite_link}`\n\n"
                "👆 *Tap and hold the link to copy.*"
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=is_auth, telegram_id=telegram_id)
        )
        
    # ==================== CONTACT ====================
        
    async def show_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show contact information and community channels for support"""
        if update.callback_query:
            await update.callback_query.answer()

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)
        first_name = update.effective_user.first_name or 'Player'

        if lang == 'am':
            content = (
                f"👋 *እንኳን ወደ Gasha Bingo የእርዳታ ማዕከል በደህና መጡ፣ {first_name}!*\n\n"
                "📞 *የደንበኞች አገልግሎት እና ድጋፍ*\n"
                "ለማንኛውም ጥያቄ፣ ችግር ወይም እርዳታ በደስታ እናገለግልዎታለን!\n\n"
                "───────────────\n"
                "📌 *የሚከተሉትን ጉዳዮች ለማንሳት ይችላሉ፦*\n"
                "• 💰 የገንዘብ ገቢ/ወጪ (Deposit/Withdrawal) ችግሮች\n"
                "• 📩 የገንዘብ ማስተላለፍ ጥያቄዎች\n"
                "• 🎮 የቢንጎ ጨዋታ ወይም የቴሌግራም ችግሮች\n"
                "• 📝 የጨዋታ ህጎች እና መመሪያዎች\n"
                "• 🎁 የግብዣ እና የቦነስ ጥያቄዎች\n"
                "• ⚠️ ሌሎች ማንኛውም ጉዳዮች\n"
                "───────────────\n\n"
                "💬 በቀጥታ ድጋፍ ያግኙ ወይም ማህበረሰባችንን ይቀላቀሉ!"
            )
            
            keyboard = [
                [InlineKeyboardButton("💬 የድጋፍ መስመር (@gasha_bingo)", url="https://t.me/gasha_bingo")],
                [InlineKeyboardButton("👥 የቴሌግራም ማህበረሰብ (Group)", url="https://t.me/+G6sILM_Sur0yYzZk")]
            ]
        else:
            content = (
                f"👋 *Welcome to Gasha Bingo Help Center, {first_name}!*\n\n"
                "📞 *Customer Support & Help Center*\n"
                "Need help or have questions? We're here to assist you!\n\n"
                "───────────────\n"
                "📌 *You can reach out for:*\n"
                "• 💰 Deposit & Withdrawal inquiries\n"
                "• 📩 Fund transfer issues\n"
                "• 🎮 Game rules or technical problems\n"
                "• 🎁 Invite & bonus questions\n"
                "• ⚠️ Any other account concerns\n"
                "───────────────\n\n"
                "💬 Contact direct support or join our official group below!"
            )

            keyboard = [
                [InlineKeyboardButton("💬 Direct Support (@gasha_bingo)", url="https://t.me/gasha_bingo")],
                [InlineKeyboardButton("👥 Telegram Group", url="https://t.me/+G6sILM_Sur0yYzZk")]
            ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
        
    # ==================== TRANSFER ====================

    async def show_transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        chat_id = update.effective_chat.id
        telegram_id = str(update.effective_user.id)
        lang = self.get_user_language(telegram_id)

        # Check if user exists in database
        user_exists, result = await self.check_user_exists(telegram_id)
        if not user_exists:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
            )
            return

        if lang == 'am':
            content = "📩 *ገንዘብ ማስተላለፍ*\n\nየተጫዋች ወደ ተጫዋች ገንዘብ ማስተላለፍ በቅርቡ ይጀመራል!"
        else:
            content = "📩 *Transfer Funds*\n\nPlayer-to-player transfers are coming soon!"

        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            parse_mode='Markdown',
            reply_markup=self.get_persistent_reply_keyboard(is_auth=self.is_authenticated(telegram_id), telegram_id=telegram_id)
        )

    # ==================== CANCEL ====================

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = update.effective_chat.id
        telegram_id = str(user.id)
        lang = self.get_user_language(telegram_id)

        if update.callback_query:
            await update.callback_query.answer()

        is_auth = self.is_authenticated(telegram_id)
        content = "❌ ተግባሩ ተሰርዟል።" if lang == 'am' else "❌ Operation cancelled."
        await context.bot.send_message(
            chat_id=chat_id,
            text=content,
            reply_markup=self.get_persistent_reply_keyboard(is_auth=is_auth, telegram_id=telegram_id)
        )

        context.user_data.clear()
        return ConversationHandler.END