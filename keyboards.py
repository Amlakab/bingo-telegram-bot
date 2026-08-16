from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu_keyboard():
    """Main menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("🎮 Play Bingo", callback_data='play'),
            InlineKeyboardButton("💰 Wallet", callback_data='wallet')
        ],
        [
            InlineKeyboardButton("📊 History", callback_data='history'),
            InlineKeyboardButton("👤 Profile", callback_data='profile')
        ],
        [
            InlineKeyboardButton("🚪 Logout", callback_data='logout')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_wallet_keyboard():
    """Wallet menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("💰 Deposit", callback_data='deposit'),
            InlineKeyboardButton("💳 Withdraw", callback_data='withdraw')
        ],
        [
            InlineKeyboardButton("📊 Transaction History", callback_data='history')
        ],
        [
            InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    """Back to menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    """Cancel operation keyboard"""
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_transaction_status_emoji(status):
    """Get emoji for transaction status"""
    if status == 'completed':
        return '✅'
    elif status == 'pending':
        return '⏳'
    else:
        return '❌'

def get_transaction_type_emoji(type_):
    """Get emoji for transaction type"""
    if type_ in ['deposit', 'winning']:
        return '🟢'
    else:
        return '🔴'