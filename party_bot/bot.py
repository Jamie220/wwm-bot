import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from pathlib import Path
import database as db


# ============================================================
# ENV
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

load_dotenv(ROOT_DIR / ".env")

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN was not found in .env")


# ============================================================
# CONFIG
# ============================================================

# Discord Server ID
GUILD_ID = 1444137048117215535

# #general Channel ID
GENERAL_CHANNEL_ID = 1444137048574263430

# Reminder X minutes before party starts
REMINDER_MINUTES_BEFORE = 5

# Scheduler check interval
REMINDER_CHECK_SECONDS = 30

# Party timezone
PARTY_TIMEZONE = ZoneInfo("Australia/Melbourne")


# ============================================================
# UI TEXT
# ============================================================

TEXT = {
    # General
    "today": "今天 / Today",
    "tomorrow": "明天 / Tomorrow",
    "none": "暂无 / None",

    # Party embed
    "start_time": "🕚 发车时间 / Start Time",
    "player_count": "👥 正式人数 / Party Players",
    "organizer": "👤 组织者 / Organizer",
    "members": "⚔️ 正式成员 / Party Members",
    "helpers": "🛠️ 可黑工 / Helpers",
    "status": "📌 状态 / Status",
    "party_full": "✅ 队伍已满 / Party Full",

    # Footer
    "footer": (
        "Join = 正式参战 / Party Member ｜ "
        "可黑工 = 可支援但不计入人数 / Helper, not counted"
    ),
}


# ============================================================
# ACTIVE PARTIES
# ============================================================

active_parties = []
database_restored = False

# ============================================================
# BOT SETUP
# ============================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# TIME FUNCTIONS
# ============================================================

def parse_party_time(time_string: str):
    """
    Convert HH:MM into the next occurrence of that time
    in PARTY_TIMEZONE.

    Example:
    Current time: 19:00
    Input: 23:00
    -> Today 23:00

    Current time: 23:30
    Input: 00:30
    -> Tomorrow 00:30
    """

    try:
        parsed_time = datetime.strptime(
            time_string,
            "%H:%M"
        ).time()

    except ValueError:
        return None

    now = datetime.now(PARTY_TIMEZONE)

    start_datetime = datetime.combine(
        now.date(),
        parsed_time,
        tzinfo=PARTY_TIMEZONE
    )

    # If that time has already passed today,
    # use tomorrow instead
    if start_datetime <= now:
        start_datetime += timedelta(days=1)

    return start_datetime


def format_party_datetime(dt: datetime):
    """
    Display time with bilingual day label.
    """

    now = datetime.now(PARTY_TIMEZONE)

    if dt.date() == now.date():
        day_text = TEXT["today"]

    elif dt.date() == (now + timedelta(days=1)).date():
        day_text = TEXT["tomorrow"]

    else:
        day_text = dt.strftime("%d/%m")

    return f"{day_text} {dt.strftime('%H:%M')}"


# ============================================================
# CHANGE MAX PLAYERS MODAL
# ============================================================

class ChangeMaxModal(
    discord.ui.Modal,
    title="修改人数 / Change Max Players"
):

    new_max = discord.ui.TextInput(
        label="新人数上限 / New maximum players",
        placeholder="例如 / e.g. 3 / 5 / 10",
        required=True,
        max_length=2
    )

    def __init__(self, party_view):
        super().__init__()
        self.party_view = party_view

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        try:
            new_max = int(self.new_max.value)

        except ValueError:

            await interaction.response.send_message(
                "❌ 请输入有效数字。\n"
                "Please enter a valid number.",
                ephemeral=True
            )
            return

        if new_max < 1 or new_max > 50:

            await interaction.response.send_message(
                "❌ 人数上限必须在 1–50 之间。\n"
                "Maximum players must be between 1 and 50.",
                ephemeral=True
            )
            return

        current_players = len(
            self.party_view.players
        )

        if new_max < current_players:

            await interaction.response.send_message(
                f"❌ 当前已有 {current_players} 名正式成员，"
                f"人数上限不能改成 {new_max}。\n"
                f"There are already {current_players} party members, "
                f"so the maximum cannot be reduced to {new_max}.",
                ephemeral=True
            )
            return

        self.party_view.max_players = new_max

        if self.party_view.party_id is not None:
            db.update_max_players(
                self.party_view.party_id,
                new_max
            )

        await self.party_view.refresh_message()

        await interaction.response.send_message(
            f"✅ 人数上限已修改为 **{new_max} 人**。\n"
            f"Maximum players changed to **{new_max}**.",
            ephemeral=True
        )


# ============================================================
# ADD PLAYER
# ============================================================

class AddPlayerSelect(discord.ui.UserSelect):

    def __init__(self, party_view):

        super().__init__(
            placeholder=(
                "选择正式成员 / "
                "Select player to add"
            ),
            min_values=1,
            max_values=1
        )

        self.party_view = party_view

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        member = self.values[0]

        if member.bot:

            await interaction.response.send_message(
                "❌ 不能添加 Bot。\n"
                "Bots cannot be added to the party.",
                ephemeral=True
            )
            return

        if member.id in self.party_view.players:

            await interaction.response.send_message(
                f"{member.mention} 已经在正式队伍里了。\n"
                f"{member.mention} is already a party member.",
                ephemeral=True
            )
            return

        if (
            len(self.party_view.players)
            >= self.party_view.max_players
        ):

            await interaction.response.send_message(
                "❌ 队伍已经满员。\n"
                "The party is already full.",
                ephemeral=True
            )
            return

        # Helper -> Party Member
        if member.id in self.party_view.helpers:
            self.party_view.helpers.remove(
                member.id
            )

        self.party_view.players.append(
            member.id
        )

        if self.party_view.party_id is not None:
            db.set_member(
                self.party_view.party_id,
                member.id,
                "player"
            )

        await self.party_view.refresh_message()

        await interaction.response.send_message(
            f"✅ 已将 {member.mention} 加入正式队伍。\n"
            f"{member.mention} has been added to the party.",
            ephemeral=True
        )


class AddPlayerView(discord.ui.View):

    def __init__(self, party_view):

        super().__init__(timeout=60)

        self.add_item(
            AddPlayerSelect(party_view)
        )


# ============================================================
# REMOVE PLAYER
# ============================================================

class RemovePlayerSelect(discord.ui.UserSelect):

    def __init__(self, party_view):

        super().__init__(
            placeholder=(
                "选择要移除的玩家 / "
                "Select player to remove"
            ),
            min_values=1,
            max_values=1
        )

        self.party_view = party_view

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        member = self.values[0]

        removed = False

        if member.id in self.party_view.players:
            self.party_view.players.remove(
                member.id
            )
            removed = True

        if member.id in self.party_view.helpers:
            self.party_view.helpers.remove(
                member.id
            )
            removed = True

        if not removed:

            await interaction.response.send_message(
                f"❌ {member.mention} 不在这个活动里。\n"
                f"{member.mention} is not registered for this party.",
                ephemeral=True
            )
            return

        if self.party_view.party_id is not None:
            db.remove_member(
                self.party_view.party_id,
                member.id
            )

        await self.party_view.refresh_message()

        await interaction.response.send_message(
            f"✅ 已将 {member.mention} 移出活动。\n"
            f"{member.mention} has been removed from the party.",
            ephemeral=True
        )


class RemovePlayerView(discord.ui.View):

    def __init__(self, party_view):

        super().__init__(timeout=60)

        self.add_item(
            RemovePlayerSelect(party_view)
        )


# ============================================================
# CANCEL CONFIRMATION
# ============================================================

class CancelConfirmView(discord.ui.View):

    def __init__(self, party_view):

        super().__init__(timeout=30)

        self.party_view = party_view

    @discord.ui.button(
        label="Confirm Cancel",
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def confirm_cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        self.party_view.cancelled = True

        if self.party_view.party_id is not None:
            db.cancel_party(
                self.party_view.party_id
            )

        for item in self.party_view.children:

            if isinstance(
                item,
                discord.ui.Button
            ):
                item.disabled = True

        await self.party_view.refresh_message()

        await interaction.response.edit_message(
            content=(
                "✅ 活动已取消。\n"
                "Party cancelled."
            ),
            view=None
        )

    @discord.ui.button(
        label="Back",
        emoji="↩️",
        style=discord.ButtonStyle.secondary
    )
    async def cancel_back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content=(
                "已取消操作。\n"
                "Action cancelled."
            ),
            view=None
        )


# ============================================================
# MANAGE VIEW
# ============================================================

class ManageView(discord.ui.View):

    def __init__(self, party_view):

        super().__init__(timeout=120)

        self.party_view = party_view

    @discord.ui.button(
        label="Add Player",
        emoji="➕",
        style=discord.ButtonStyle.success
    )
    async def add_player(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "请选择要加入正式队伍的玩家。\n"
            "Select a player to add to the party:",
            view=AddPlayerView(
                self.party_view
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="Remove Player",
        emoji="➖",
        style=discord.ButtonStyle.secondary
    )
    async def remove_player(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if (
            not self.party_view.players
            and not self.party_view.helpers
        ):

            await interaction.response.send_message(
                "当前没有玩家可以移除。\n"
                "There are no registered players to remove.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "请选择要移除的玩家。\n"
            "Select a player to remove:",
            view=RemovePlayerView(
                self.party_view
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="Change Max Players",
        emoji="👥",
        style=discord.ButtonStyle.primary
    )
    async def change_max(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            ChangeMaxModal(
                self.party_view
            )
        )

    @discord.ui.button(
        label="Cancel Party",
        emoji="❌",
        style=discord.ButtonStyle.danger
    )
    async def cancel_party(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "⚠️ 确定要取消这个活动吗？\n"
            "Are you sure you want to cancel this party?",
            view=CancelConfirmView(
                self.party_view
            ),
            ephemeral=True
        )


# ============================================================
# PARTY VIEW
# ============================================================

class PartyView(discord.ui.View):

    def __init__(
        self,
        activity_name: str,
        start_datetime: datetime,
        max_players: int,
        organizer,
        party_id=None
    ):

        super().__init__(timeout=None)

        self.party_id = party_id
        self.activity_name = activity_name
        self.start_datetime = start_datetime
        self.max_players = max_players
        self.organizer = organizer

        # Actual party members
        self.players = []

        # Helpers - not counted towards max players
        self.helpers = []

        self.message = None
        self.cancelled = False

        # Prevent duplicate reminders
        self.reminder_sent = False


    # ========================================================
    # BUILD EMBED
    # ========================================================

    def build_embed(self):

        current_players = len(
            self.players
        )

        if self.cancelled:

            embed = discord.Embed(
                title=(
                    f"❌ {self.activity_name}"
                ),
                description=(
                    "**此活动已取消 / "
                    "This party has been cancelled**"
                ),
                color=discord.Color.red()
            )

        else:

            embed = discord.Embed(
                title=(
                    f"⚔️ {self.activity_name}"
                ),
                color=discord.Color.blue()
            )

        embed.add_field(
            name=TEXT["start_time"],
            value=format_party_datetime(
                self.start_datetime
            ),
            inline=True
        )

        embed.add_field(
            name=TEXT["player_count"],
            value=(
                f"{current_players} / "
                f"{self.max_players}"
            ),
            inline=True
        )

        embed.add_field(
            name=TEXT["organizer"],
            value=self.organizer.mention,
            inline=False
        )

        # Party members
        if self.players:

            player_mentions = "\n".join(
                f"<@{user_id}>"
                for user_id in self.players
            )

        else:

            player_mentions = TEXT["none"]

        embed.add_field(
            name=TEXT["members"],
            value=player_mentions,
            inline=False
        )

        # Helpers
        if self.helpers:

            helper_mentions = "\n".join(
                f"<@{user_id}>"
                for user_id in self.helpers
            )

        else:

            helper_mentions = TEXT["none"]

        embed.add_field(
            name=TEXT["helpers"],
            value=helper_mentions,
            inline=False
        )

        # Status
        if not self.cancelled:

            if (
                current_players
                >= self.max_players
            ):

                embed.add_field(
                    name=TEXT["party_full"],
                    value=(
                        "正式成员人数已达到上限。\n"
                        "The party has reached its "
                        "maximum number of players."
                    ),
                    inline=False
                )

            else:

                remaining = (
                    self.max_players
                    - current_players
                )

                embed.add_field(
                    name=TEXT["status"],
                    value=(
                        f"还差 **{remaining}** "
                        f"名正式成员！\n"
                        f"**{remaining}** more "
                        f"player(s) needed!"
                    ),
                    inline=False
                )

            embed.set_footer(
                text=TEXT["footer"]
            )

        return embed


    # ========================================================
    # REFRESH MESSAGE
    # ========================================================

    async def refresh_message(self):

        if self.message:

            await self.message.edit(
                embed=self.build_embed(),
                view=self
            )


    # ========================================================
    # JOIN
    # ========================================================

    @discord.ui.button(
        label="Join",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="party_join"
    )
    async def join_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.cancelled:

            await interaction.response.send_message(
                "这个活动已经取消。\n"
                "This party has already been cancelled.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        if user_id in self.players:

            await interaction.response.send_message(
                "你已经是这个活动的正式成员。\n"
                "You are already a party member.",
                ephemeral=True
            )
            return

        if (
            len(self.players)
            >= self.max_players
        ):

            await interaction.response.send_message(
                "这个队伍已经满员了。\n"
                "This party is already full.",
                ephemeral=True
            )
            return

        # Helper -> Party Member
        if user_id in self.helpers:
            self.helpers.remove(
                user_id
            )

        self.players.append(
            user_id
        )

        if self.party_id is not None:
            db.set_member(
                self.party_id,
                user_id,
                "player"
            )

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )


    # ========================================================
    # HELPER
    # ========================================================

    @discord.ui.button(
        label="可黑工 / Helper",
        emoji="🛠️",
        style=discord.ButtonStyle.primary,
        custom_id="party_helper"
    )
    async def helper_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.cancelled:

            await interaction.response.send_message(
                "这个活动已经取消。\n"
                "This party has already been cancelled.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        if user_id in self.helpers:

            await interaction.response.send_message(
                "你已经登记为可黑工。\n"
                "You are already registered as a helper.",
                ephemeral=True
            )
            return

        # Party Member -> Helper
        if user_id in self.players:
            self.players.remove(
                user_id
            )

        self.helpers.append(
            user_id
        )

        if self.party_id is not None:
            db.set_member(
                self.party_id,
                user_id,
                "helper"
            )

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )


    # ========================================================
    # LEAVE
    # ========================================================

    @discord.ui.button(
        label="Leave",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
        custom_id="party_leave"
    )
    async def leave_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if self.cancelled:

            await interaction.response.send_message(
                "这个活动已经取消。\n"
                "This party has already been cancelled.",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        if user_id in self.players:

            self.players.remove(
                user_id
            )

            if self.party_id is not None:
                db.remove_member(
                    self.party_id,
                    user_id
                )

        elif user_id in self.helpers:

            self.helpers.remove(
                user_id
            )

            if self.party_id is not None:
                db.remove_member(
                    self.party_id,
                    user_id
                )

        else:

            await interaction.response.send_message(
                "你目前没有报名这个活动。\n"
                "You are not currently registered for this party.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )


    # ========================================================
    # MANAGE
    # ========================================================

    @discord.ui.button(
        label="Manage",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        custom_id="party_manage"
    )
    async def manage_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if (
            interaction.user.id
            != self.organizer.id
        ):

            await interaction.response.send_message(
                "🔒 只有活动组织者可以管理这个活动。\n"
                "Only the party organizer can manage this party.",
                ephemeral=True
            )
            return

        if self.cancelled:

            await interaction.response.send_message(
                "这个活动已经取消。\n"
                "This party has already been cancelled.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"⚙️ **管理 / Manage: "
            f"{self.activity_name}**\n\n"
            f"正式成员 / Party Members: "
            f"{len(self.players)} / "
            f"{self.max_players}\n"
            f"可黑工 / Helpers: "
            f"{len(self.helpers)}",
            view=ManageView(self),
            ephemeral=True
        )


# ============================================================
# REMINDER FUNCTION
# ============================================================

async def send_party_reminder(party):

    # Don't send twice
    if party.reminder_sent:
        return

    # Don't remind cancelled party
    if party.cancelled:
        return

    # Mark first to protect against duplicate scheduler runs
    party.reminder_sent = True

    if party.party_id is not None:
        db.mark_reminder_sent(
            party.party_id
        )

    # Nobody joined
    if not party.players:

        print(
            f"ℹ️ Reminder skipped: "
            f"{party.activity_name} has no players."
        )

        return

    channel = bot.get_channel(
        GENERAL_CHANNEL_ID
    )

    if channel is None:

        print(
            "❌ General channel could not be found. "
            "Check GENERAL_CHANNEL_ID."
        )

        # Allow retry
        party.reminder_sent = False

        if party.party_id is not None:
            db.reset_reminder(
                party.party_id
            )

        return

    mentions = " ".join(
        f"<@{user_id}>"
        for user_id in party.players
    )

    now = datetime.now(
        PARTY_TIMEZONE
    )

    minutes_remaining = (
        party.start_datetime - now
    ).total_seconds() / 60

    # Created inside reminder window
    if (
        minutes_remaining
        < REMINDER_MINUTES_BEFORE
    ):

        message = (
            f"🔔 **{party.activity_name} 即将发车！ "
            f"/ Starting Soon!**\n\n"
            f"{mentions}\n\n"
            f"距离发车不足 "
            f"**{REMINDER_MINUTES_BEFORE} 分钟**，"
            f"请准备上线。\n"
            f"Less than "
            f"**{REMINDER_MINUTES_BEFORE} minutes** "
            f"until start. Please get online and ready.\n\n"
            f"🕚 发车时间 / Start Time: "
            f"**{party.start_datetime.strftime('%H:%M')}**"
        )

    else:

        message = (
            f"🔔 **{party.activity_name} "
            f"还有 {REMINDER_MINUTES_BEFORE} 分钟发车！**\n"
            f"**{party.activity_name} starts in "
            f"{REMINDER_MINUTES_BEFORE} minutes!**\n\n"
            f"{mentions}\n\n"
            f"请准备上线。\n"
            f"Please get online and ready.\n\n"
            f"🕚 发车时间 / Start Time: "
            f"**{party.start_datetime.strftime('%H:%M')}**"
        )

    try:

        await channel.send(
            message,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=False
            )
        )

        print(
            f"🔔 Reminder sent: "
            f"{party.activity_name}"
        )

    except Exception as e:

        print(
            f"❌ Failed to send reminder: {e}"
        )

        # Allow scheduler to retry
        party.reminder_sent = False

        if party.party_id is not None:
            db.reset_reminder(
                party.party_id
            )


# ============================================================
# REMINDER SCHEDULER
# ============================================================

@tasks.loop(
    seconds=REMINDER_CHECK_SECONDS
)
async def reminder_scheduler():

    now = datetime.now(
        PARTY_TIMEZONE
    )

    for party in active_parties.copy():

        # Party already finished
        if now > party.start_datetime:

            if party.party_id is not None:
                db.complete_party(
                    party.party_id
                )

            active_parties.remove(
                party
            )

            print(
                f"🧹 Party completed: "
                f"{party.activity_name}"
            )

            continue

        # Ignore cancelled parties
        if party.cancelled:
            continue

        # Already reminded
        if party.reminder_sent:
            continue

        reminder_time = (
            party.start_datetime
            - timedelta(
                minutes=REMINDER_MINUTES_BEFORE
            )
        )

        if now >= reminder_time:

            if now <= party.start_datetime:

                await send_party_reminder(
                    party
                )


@reminder_scheduler.before_loop
async def before_reminder_scheduler():

    await bot.wait_until_ready()


# ============================================================
# RECOVER DATABASE
# ============================================================

async def restore_parties():

    global database_restored

    if database_restored:
        return

    database_restored = True

    rows = db.get_active_parties()

    print(
        f"💾 Found {len(rows)} active party(s) "
        f"in database."
    )

    now = datetime.now(
        PARTY_TIMEZONE
    )

    for row in rows:

        start_datetime = datetime.fromisoformat(
            row["start_datetime"]
        )

        # Ignore parties that have already finished
        if start_datetime <= now:

            db.complete_party(
                row["id"]
            )

            continue

        guild = bot.get_guild(
            row["guild_id"]
        )

        if guild is None:
            continue

        channel = bot.get_channel(
            row["channel_id"]
        )

        if channel is None:
            continue

        try:

            message = await channel.fetch_message(
                row["message_id"]
            )

        except discord.NotFound:

            print(
                f"⚠️ Party message "
                f"{row['message_id']} no longer exists."
            )

            continue

        organizer = guild.get_member(
            row["organizer_id"]
        )

        if organizer is None:

            try:

                organizer = await guild.fetch_member(
                    row["organizer_id"]
                )

            except discord.NotFound:
                continue

        view = PartyView(
            activity_name=row["activity_name"],
            start_datetime=start_datetime,
            max_players=row["max_players"],
            organizer=organizer,
            party_id=row["id"]
        )

        view.message = message

        view.cancelled = bool(
            row["cancelled"]
        )

        view.reminder_sent = bool(
            row["reminder_sent"]
        )

        members = db.get_party_members(
            row["id"]
        )

        for member in members:

            if (
                member["member_type"]
                == "player"
            ):

                view.players.append(
                    member["user_id"]
                )

            elif (
                member["member_type"]
                == "helper"
            ):

                view.helpers.append(
                    member["user_id"]
                )

        # Register persistent buttons
        bot.add_view(
            view,
            message_id=row["message_id"]
        )

        active_parties.append(
            view
        )

        # Refresh original Discord message
        await view.refresh_message()

        print(
            f"♻️ Restored: "
            f"{view.activity_name} | "
            f"{len(view.players)}/"
            f"{view.max_players}"
        )


# ============================================================
# TEST COMMAND
# ============================================================

@bot.tree.command(
    name="test",
    description="Check whether WWM Party Bot is online"
)
async def test(
    interaction: discord.Interaction
):

    await interaction.response.send_message(
        "✅ WWM Party Bot is online!\n"
        "机器人运行正常！",
        ephemeral=True
    )


# ============================================================
# PARTY COMMAND
# ============================================================

@bot.tree.command(
    name="party",
    description="创建组队 / Create a WWM party"
)
@app_commands.describe(
    activity=(
        "活动名称 / Activity name, "
        "例如 / e.g. 百业十人本"
    ),
    time=(
        "发车时间 / Start time, "
        "24小时制 / 24-hour format, e.g. 23:00"
    ),
    max_players=(
        "正式人数上限 / Maximum party members, "
        "例如 / e.g. 3 or 10"
    )
)
async def party(
    interaction: discord.Interaction,
    activity: str,
    time: str,
    max_players: app_commands.Range[
        int,
        1,
        50
    ]
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "这个命令只能在服务器中使用。\n"
            "This command can only be used inside a server.",
            ephemeral=True
        )

        return

    # -------------------------
    # Parse / validate time
    # -------------------------

    start_datetime = parse_party_time(
        time.strip()
    )

    if start_datetime is None:

        await interaction.response.send_message(
            "❌ **时间格式不正确 / Invalid time format**\n\n"
            "请使用24小时制 `HH:MM`\n"
            "Please use 24-hour format `HH:MM`\n\n"
            "例如 / Examples: "
            "`20:00`, `23:30`, `00:30`",
            ephemeral=True
        )

        return

    # -------------------------
    # Create party
    # -------------------------

    view = PartyView(
        activity_name=activity,
        start_datetime=start_datetime,
        max_players=max_players,
        organizer=interaction.user
    )

    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view
    )

    view.message = (
        await interaction.original_response()
    )

    # Save party to database
    view.party_id = db.create_party(
        guild_id=interaction.guild.id,
        channel_id=view.message.channel.id,
        message_id=view.message.id,
        activity_name=view.activity_name,
        start_datetime=(
            view.start_datetime.isoformat()
        ),
        max_players=view.max_players,
        organizer_id=interaction.user.id,
        created_at=(
            datetime.now(
                PARTY_TIMEZONE
            ).isoformat()
        )
    )

    active_parties.append(
        view
    )

    print(
        f"🎮 Party created: "
        f"{activity} | "
        f"{start_datetime.isoformat()} | "
        f"Max {max_players}"
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print(
        f"✅ Logged in as {bot.user}"
    )

    print(
        f"✅ Bot ID: {bot.user.id}"
    )

    print(
        f"🕒 Party timezone: "
        f"{PARTY_TIMEZONE}"
    )

    print(
        f"🔔 Reminder: "
        f"{REMINDER_MINUTES_BEFORE} "
        f"minutes before"
    )

    guild = discord.Object(
        id=GUILD_ID
    )

    try:

        bot.tree.copy_global_to(
            guild=guild
        )

        synced = await bot.tree.sync(
            guild=guild
        )

        print(
            f"✅ Synced {len(synced)} "
            f"slash command(s) "
            f"to guild {GUILD_ID}"
        )

        for command in synced:

            print(
                f"   /{command.name}"
            )

    except Exception as e:

        print(
            f"❌ Failed to sync commands: {e}"
        )

    await restore_parties()

    if not reminder_scheduler.is_running():

        reminder_scheduler.start()

        print(
            f"✅ Reminder scheduler started "
            f"(check every "
            f"{REMINDER_CHECK_SECONDS}s)"
        )


# ============================================================
# START BOT
# ============================================================

db.init_database()

bot.run(TOKEN)