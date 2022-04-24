"""All bot stuff is in this file."""
import asyncio
import configparser
import logging
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_handler_backends import State, StatesGroup
from telebot.asyncio_storage import StatePickleStorage
from anchor_binding.anchor import AnchorAPI
import os
import gettext

translation = gettext.translation('counter', 'pots', fallback=True)
_, ngettext = translation.gettext, translation.ngettext

cwd = os.getcwd()
print(cwd)

# TODO : THIS IS A BODGE GET RID OF THIS ASAP
users = set()

logging.basicConfig(level=logging.DEBUG)

config = configparser.ConfigParser()
with open("config.cfg"):
    config.read("config.cfg")

bot = AsyncTeleBot(
    config["TELEGRAM"]["API_TOKEN"],
    parse_mode="MARKDOWN",
    state_storage=StatePickleStorage(),
)


class BotStates(StatesGroup):  # noqa: R0903
    """All bot states."""

    monitoring_state = State()
    adding_apy = State()
    naming_notifier = State()


@bot.message_handler(commands=["start", "help"])
async def greet_threshhold(message):
    """Greet a new user and specify all commands"""
    asyncio.gather(
        bot.set_state(
            message.from_user.id, BotStates.monitoring_state, message.chat.id
        ),
        bot.send_message(
            message.chat.id,
            _("""
Hi! Welcome to anchorChecker bot!
Right now it supports notifies for the following commands:
/apy - add a new APY notifier
/reserve - 
/list - list all current notifiers
/help - show this help
Right now the updates it's APY once in an hour
    """),
        ),
    )


@bot.message_handler(commands=["apy"])
async def poll_threshhold(message):
    """Write the prompt to enter threshhold, set state to recieving the answer."""
    asyncio.gather(
        bot.set_state(message.from_user.id, BotStates.adding_apy, message.chat.id),
        bot.send_message(message.chat.id, _("Input your threshold:")),
    )


@bot.message_handler(state=BotStates.adding_apy)
async def register_user(message):
    """Add user to state backend."""
    # TODO: проверить что похоже на число и/или процент регэкспом
    async with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data["threshold"] = float(message.text)
        users.add((message.from_user.id, message.chat.id))
    asyncio.gather(
        bot.set_state(message.from_user.id, BotStates.naming_notifier, message.chat.id),
        bot.send_message(message.chat.id, _("Input threshhold's name")),
    )


@bot.message_handler(state=BotStates.naming_notifier)
async def name_notifier(message):
    """Add docstring"""
    async with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        if data.get("threshold"):
            data[message.text] = data["threshold"]
            del data["threshold"]
            logging.debug(
                _("added thershhold name {} with value {}").format(message.text, data[message.text])
            )
        else:
            # TODO: throw exception
            pass
    await bot.set_state(
        message.from_user.id, BotStates.monitoring_state, message.chat.id
    )


@bot.message_handler(state=BotStates.monitoring_state, commands=["list"])
async def list_notifiers(message):
    """List all notifiers for a user."""
    async with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        # logging.debug(data)
        if data:
            for notifier in data.items():
                logging.debug(_("found notifier: {}").format(notifier))
                await bot.send_message(message.chat.id, _("found notifier: {}").format(notifier))
        else:
            await bot.send_message(message.chat.id, _("No notifiers set yet"))


async def run_notifications():
    """Query the Anchor API and go through users to send if APY drops."""
    apy = AnchorAPI("./anchor_binding/app").get_balance()
    for user_cred in users:
        async with bot.retrieve_data(*user_cred) as data:
            for notifier, amount in data.items():
                if apy["APY"] < amount:
                    await bot.send_message(
                        user_cred[1], _("Alarm! APY dropped below {} on notifier {}").format(amount, notifier)
                    )


async def scheduler_process():
    """Routine to query notifications-wait an hour-repeat."""
    while True:
        await run_notifications()
        await asyncio.sleep(3600)


async def main():
    """Gather all needed tasks in bot loop."""
    await asyncio.gather(bot.infinity_polling(), scheduler_process())