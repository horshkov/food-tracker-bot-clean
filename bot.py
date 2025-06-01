import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
import openai
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize AI clients
claude = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_KEY')
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        supabase.table('users').upsert({
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        }).execute()
    except Exception as e:
        logger.error(f"Error adding user to database: {str(e)}")
    welcome_message = (
        f"👋 Hi {user.first_name}!\n\n"
        "I'm your Food Tracker Bot. I can help you analyze your food and track your nutrition.\n\n"
        "Here's what I can do:\n"
        "📝 Type a description of your food\n"
        "📊 Use /stats to see your nutrition statistics\n"
        "📜 Use /history to see your recent food entries\n"
        "❓ Use /help for more information"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Food Tracker Bot Help\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/stats - Show your nutrition statistics\n"
        "/history - Show your recent food entries\n"
        "/delete - Delete a food entry\n\n"
        "Features:\n"
        "• Type food descriptions for analysis\n"
        "• Track your nutrition history\n"
        "• View your nutrition statistics"
    )
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        response = supabase.table('food_entries').select(
            'calories, protein, carbs, fats'
        ).eq('user_id', user_id).execute()
        entries = response.data
        if not entries:
            await update.message.reply_text("You haven't tracked any food yet. Send me a description to get started!")
            return
        total_entries = len(entries)
        total_calories = sum(entry['calories'] for entry in entries)
        total_protein = sum(entry['protein'] for entry in entries)
        total_carbs = sum(entry['carbs'] for entry in entries)
        total_fats = sum(entry['fats'] for entry in entries)
        avg_calories = total_calories / total_entries
        avg_protein = total_protein / total_entries
        avg_carbs = total_carbs / total_entries
        avg_fats = total_fats / total_entries
        stats_message = (
            "📊 Your Nutrition Statistics\n\n"
            f"Total Entries: {total_entries}\n\n"
            "📈 Totals:\n"
            f"Calories: {int(total_calories)} kcal\n"
            f"Protein: {total_protein:.1f}g\n"
            f"Carbs: {total_carbs:.1f}g\n"
            f"Fats: {total_fats:.1f}g\n\n"
            "📊 Averages (per entry):\n"
            f"Calories: {avg_calories:.1f} kcal\n"
            f"Protein: {avg_protein:.1f}g\n"
            f"Carbs: {avg_carbs:.1f}g\n"
            f"Fats: {avg_fats:.1f}g"
        )
        await update.message.reply_text(stats_message)
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        await update.message.reply_text("❌ Sorry, there was an error getting your statistics.")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        response = supabase.table('food_entries').select(
            'id, description, calories, protein, carbs, fats, created_at'
        ).eq('user_id', user_id).order('created_at', desc=True).limit(10).execute()
        entries = response.data
        if not entries:
            await update.message.reply_text("You haven't tracked any food yet. Send me a description to get started!")
            return
        history_message = "📜 Your Recent Food History\n\n"
        for entry in entries:
            created_at = datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
            history_message += (
                f"ID: {entry['id']}\n"
                f"🍽 {entry['description']}\n"
                f"Calories: {entry['calories']} kcal\n"
                f"Protein: {entry['protein']}g | Carbs: {entry['carbs']}g | Fats: {entry['fats']}g\n"
                f"Date: {created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            )
        history_message += "\nTo delete an entry, use /delete <ID>"
        await update.message.reply_text(history_message)
    except Exception as e:
        logger.error(f"Error getting history: {str(e)}")
        await update.message.reply_text("❌ Sorry, there was an error getting your history.")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Please provide an entry ID to delete.\n"
            "Example: /delete 123\n\n"
            "Use /history to see your entries with their IDs."
        )
        return
    try:
        entry_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid entry ID (a number).")
        return
    user_id = update.effective_user.id
    try:
        response = supabase.table('food_entries').select(
            'id, description, calories, protein, carbs, fats, created_at'
        ).eq('id', entry_id).eq('user_id', user_id).execute()
        entry = response.data[0] if response.data else None
        if not entry:
            await update.message.reply_text("Entry not found. Please check the ID and try again.")
            return
        supabase.table('food_entries').delete().eq('id', entry_id).eq('user_id', user_id).execute()
        created_at = datetime.fromisoformat(entry['created_at'].replace('Z', '+00:00'))
        await update.message.reply_text(
            f"✅ Entry deleted successfully:\n\n"
            f"ID: {entry['id']}\n"
            f"🍽 {entry['description']}\n"
            f"Calories: {entry['calories']} kcal\n"
            f"Protein: {entry['protein']}g | Carbs: {entry['carbs']}g | Fats: {entry['fats']}g\n"
            f"Date: {created_at.strftime('%Y-%m-%d %H:%M')}"
        )
    except Exception as e:
        logger.error(f"Error deleting entry: {str(e)}")
        await update.message.reply_text("❌ Failed to delete the entry. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    await update.message.chat.send_action(action="typing")
    try:
        try:
            response = claude.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1000,
                temperature=0,
                system="You are a nutrition expert. Provide accurate nutritional analysis of food items.",
                messages=[
                    {"role": "user", "content": f"""Please analyze the following food description and provide nutritional information in a structured format:\n\nFood: {text}\n\nPlease provide:\n1. Estimated calories\n2. Protein content in grams\n3. Carbohydrates in grams\n4. Fats in grams\n5. A brief analysis of the meal's nutritional value\n\nFormat your response as JSON with the following structure:\n{{\n    \"calories\": number,\n    \"protein\": number,\n    \"carbs\": number,\n    \"fats\": number,\n    \"analysis\": \"string\"\n}}"""}
                ]
            )
            analysis = response.content[0].text
        except Exception as e:
            logger.warning(f"Claude analysis failed, trying OpenAI: {str(e)}")
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a nutrition expert. Provide accurate nutritional analysis of food items."},
                    {"role": "user", "content": f"""Please analyze the following food description and provide nutritional information in a structured format:\n\nFood: {text}\n\nPlease provide:\n1. Estimated calories\n2. Protein content in grams\n3. Carbohydrates in grams\n4. Fats in grams\n5. A brief analysis of the meal's nutritional value\n\nFormat your response as JSON with the following structure:\n{{\n    \"calories\": number,\n    \"protein\": number,\n    \"carbs\": number,\n    \"fats\": number,\n    \"analysis\": \"string\"\n}}"""}
                ]
            )
            analysis = response.choices[0].message.content
        import json
        import re
        json_match = re.search(r'\{.*\}', analysis, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            raise ValueError("Could not parse AI response")
        try:
            supabase.table('food_entries').insert({
                'user_id': user_id,
                'description': text,
                'calories': analysis['calories'],
                'protein': analysis['protein'],
                'carbs': analysis['carbs'],
                'fats': analysis['fats'],
                'analysis': analysis['analysis']
            }).execute()
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
        response_text = (
            f"🍽️ Food Analysis Results:\n\n"
            f"📊 Nutritional Information:\n"
            f"• Calories: {analysis['calories']} kcal\n"
            f"• Protein: {analysis['protein']}g\n"
            f"• Carbs: {analysis['carbs']}g\n"
            f"• Fats: {analysis['fats']}g\n\n"
            f"📝 Analysis:\n{analysis['analysis']}"
        )
        await update.message.reply_text(response_text)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't analyze your food entry. Please try again with a different description."
        )

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("No token provided. Please set TELEGRAM_BOT_TOKEN in .env file")
        return
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Webhook setup for Railway
    port = int(os.environ.get("PORT", 8443))
    url = os.environ.get("WEBHOOK_URL", "https://food-tracker-bot-production.up.railway.app")
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=f"{url}/webhook/{token}"
    )

if __name__ == '__main__':
    main() 