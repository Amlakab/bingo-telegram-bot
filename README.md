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

    # Register user with referral
    response = api.register_user(
        phone=phone, 
        password=password, 
        tg_id=tg_id,
        agent_id=referral_id  # ✅ Pass referral as agent_id
    )

    if response['success']:
        data = response['data']
        token = data.get('token')
        user_data = data.get('user', {})

        if token and user_data:
            # ✅ OVERWRITE the old session with new token
            logger.info(f"🔄 New session created for user {telegram_id}")
            logger.info(f"   New token: {token[:20]}...")
            
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
            # Using wallet_balance directly as bonus = wallet per your requirement
            bonus_amount = wallet_balance

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
            
            # ✅ Clear referral data after successful registration
            context.user_data.pop('referral_id', None)
            context.user_data.clear()
            return ConversationHandler.END
        else:
            error_msg = response.get('message', 'Registration failed - invalid response')
    else:
        error_msg = response.get('message', 'Registration failed')

    content = f"❌ ምዝገባው አልተሳካም: {error_msg}" if lang == 'am' else f"❌ Registration failed: {error_msg}"
    await context.bot.send_message(
        chat_id=chat_id,
        text=content,
        reply_markup=self.get_persistent_reply_keyboard(is_auth=False, telegram_id=telegram_id)
    )
    context.user_data.clear()
    return ConversationHandler.END