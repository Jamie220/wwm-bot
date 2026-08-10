import os

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv


# =========================
# ENV / CONFIG
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")


GUILD_ID = 1444137048117215535

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN was not found in .env")


# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# CHANGE MAX PLAYERS MODAL
# ============================================================

class ChangeMaxModal(discord.ui.Modal, title="Change Max Players"):

    new_max = discord.ui.TextInput(
        label="New maximum players",
        placeholder="例如：3 / 5 / 10",
        required=True,
        max_length=2
    )

    def __init__(self, party_view):
        super().__init__()
        self.party_view = party_view

    async def on_submit(self, interaction: discord.Interaction):

        try:
            new_max = int(self.new_max.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ 请输入有效数字。",
                ephemeral=True
            )
            return

        if new_max < 1 or new_max > 50:
            await interaction.response.send_message(
                "❌ 人数上限必须在 1–50 之间。",
                ephemeral=True
            )
            return

        current_players = len(self.party_view.players)

        if new_max < current_players:
            await interaction.response.send_message(
                f"❌ 当前已有 {current_players} 名正式成员，"
                f"人数上限不能改成 {new_max}。",
                ephemeral=True
            )
            return

        self.party_view.max_players = new_max

        await self.party_view.refresh_message()

        await interaction.response.send_message(
            f"✅ 人数上限已修改为 **{new_max} 人**。",
            ephemeral=True
        )


# ============================================================
# ADD PLAYER SELECT
# ============================================================

class AddPlayerSelect(discord.ui.UserSelect):

    def __init__(self, party_view):
        super().__init__(
            placeholder="选择要加入正式队伍的玩家",
            min_values=1,
            max_values=1
        )

        self.party_view = party_view

    async def callback(self, interaction: discord.Interaction):

        member = self.values[0]

        if member.bot:
            await interaction.response.send_message(
                "❌ 不能添加 Bot。",
                ephemeral=True
            )
            return

        if member.id in self.party_view.players:
            await interaction.response.send_message(
                f"{member.mention} 已经在正式队伍里了。",
                ephemeral=True
            )
            return

        if len(self.party_view.players) >= self.party_view.max_players:
            await interaction.response.send_message(
                "❌ 队伍已经满员。",
                ephemeral=True
            )
            return

        # 如果原本在可黑工名单，转为正式成员
        if member.id in self.party_view.helpers:
            self.party_view.helpers.remove(member.id)

        self.party_view.players.append(member.id)

        await self.party_view.refresh_message()

        await interaction.response.send_message(
            f"✅ 已将 {member.mention} 加入正式队伍。",
            ephemeral=True
        )


class AddPlayerView(discord.ui.View):

    def __init__(self, party_view):
        super().__init__(timeout=60)

        self.add_item(
            AddPlayerSelect(party_view)
        )


# ============================================================
# REMOVE PLAYER SELECT
# ============================================================

class RemovePlayerSelect(discord.ui.UserSelect):

    def __init__(self, party_view):
        super().__init__(
            placeholder="选择要移除的玩家",
            min_values=1,
            max_values=1
        )

        self.party_view = party_view

    async def callback(self, interaction: discord.Interaction):

        member = self.values[0]

        removed = False

        if member.id in self.party_view.players:
            self.party_view.players.remove(member.id)
            removed = True

        if member.id in self.party_view.helpers:
            self.party_view.helpers.remove(member.id)
            removed = True

        if not removed:
            await interaction.response.send_message(
                f"❌ {member.mention} 不在这个活动里。",
                ephemeral=True
            )
            return

        await self.party_view.refresh_message()

        await interaction.response.send_message(
            f"✅ 已将 {member.mention} 移出活动。",
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

        # Disable main party buttons
        for item in self.party_view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        await self.party_view.refresh_message()

        await interaction.response.edit_message(
            content="✅ 活动已取消。",
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
            content="已取消操作。",
            view=None
        )


# ============================================================
# ORGANIZER MANAGEMENT PANEL
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
            "请选择要加入正式队伍的玩家：",
            view=AddPlayerView(self.party_view),
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

        if not self.party_view.players and not self.party_view.helpers:

            await interaction.response.send_message(
                "当前没有玩家可以移除。",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "请选择要移除的玩家：",
            view=RemovePlayerView(self.party_view),
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
            ChangeMaxModal(self.party_view)
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
            "⚠️ 确定要取消这个活动吗？",
            view=CancelConfirmView(self.party_view),
            ephemeral=True
        )


# ============================================================
# PARTY VIEW
# ============================================================

class PartyView(discord.ui.View):

    def __init__(
        self,
        activity_name: str,
        start_time: str,
        max_players: int,
        organizer: discord.Member
    ):

        super().__init__(timeout=None)

        self.activity_name = activity_name
        self.start_time = start_time
        self.max_players = max_players
        self.organizer = organizer

        # 正式成员
        self.players = []

        # 可黑工，不计入正式人数
        self.helpers = []

        self.message = None
        self.cancelled = False


    # ========================================================
    # BUILD EMBED
    # ========================================================

    def build_embed(self):

        current_players = len(self.players)

        if self.cancelled:

            embed = discord.Embed(
                title=f"❌ {self.activity_name}",
                description="**此活动已取消**",
                color=discord.Color.red()
            )

        else:

            embed = discord.Embed(
                title=f"⚔️ {self.activity_name}",
                color=discord.Color.blue()
            )

        embed.add_field(
            name="🕚 发车时间",
            value=self.start_time,
            inline=True
        )

        embed.add_field(
            name="👥 正式人数",
            value=f"{current_players} / {self.max_players}",
            inline=True
        )

        embed.add_field(
            name="👤 组织者",
            value=self.organizer.mention,
            inline=False
        )

        # -------------------------
        # 正式成员名单
        # -------------------------

        if self.players:

            player_mentions = "\n".join(
                f"<@{user_id}>"
                for user_id in self.players
            )

        else:

            player_mentions = "暂无"

        embed.add_field(
            name="⚔️ 正式成员",
            value=player_mentions,
            inline=False
        )

        # -------------------------
        # 可黑工名单
        # -------------------------

        if self.helpers:

            helper_mentions = "\n".join(
                f"<@{user_id}>"
                for user_id in self.helpers
            )

        else:

            helper_mentions = "暂无"

        embed.add_field(
            name="🛠️ 可黑工",
            value=helper_mentions,
            inline=False
        )

        # -------------------------
        # Status
        # -------------------------

        if not self.cancelled:

            if current_players >= self.max_players:

                embed.add_field(
                    name="✅ 队伍已满",
                    value="正式成员人数已达到上限。",
                    inline=False
                )

            else:

                remaining = self.max_players - current_players

                embed.add_field(
                    name="📌 状态",
                    value=f"还差 **{remaining}** 名正式成员！",
                    inline=False
                )

            embed.set_footer(
                text="Join = 正式参战 ｜ 可黑工 = 可支援但不计入人数"
            )

        return embed


    # ========================================================
    # REFRESH ORIGINAL PARTY MESSAGE
    # ========================================================

    async def refresh_message(self):

        if self.message:

            await self.message.edit(
                embed=self.build_embed(),
                view=self
            )


    # ========================================================
    # BUTTON STATUS
    # ========================================================

    def update_buttons(self):

        # Keep Join / Helper / Leave active
        self.join_button.disabled = False
        self.helper_button.disabled = False
        self.leave_button.disabled = False


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
                "这个活动已经取消。",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 已经是正式成员
        if user_id in self.players:

            await interaction.response.send_message(
                "你已经是这个活动的正式成员。",
                ephemeral=True
            )
            return

        # 队伍已满
        if len(self.players) >= self.max_players:

            await interaction.response.send_message(
                "这个队伍已经满员了。",
                ephemeral=True
            )
            return

        # 如果原本是可黑工，则转为正式成员
        if user_id in self.helpers:
            self.helpers.remove(user_id)

        self.players.append(user_id)

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )


    # ========================================================
    # HELPER / 可黑工
    # ========================================================

    @discord.ui.button(
        label="可黑工",
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
                "这个活动已经取消。",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 已经在可黑工名单
        if user_id in self.helpers:

            await interaction.response.send_message(
                "你已经登记为可黑工。",
                ephemeral=True
            )
            return

        # 如果原本是正式成员，则转为可黑工
        if user_id in self.players:
            self.players.remove(user_id)

        self.helpers.append(user_id)

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
                "这个活动已经取消。",
                ephemeral=True
            )
            return

        user_id = interaction.user.id

        if user_id in self.players:

            self.players.remove(user_id)

        elif user_id in self.helpers:

            self.helpers.remove(user_id)

        else:

            await interaction.response.send_message(
                "你目前没有报名这个活动。",
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

        # ONLY ORGANIZER CAN ACCESS
        if interaction.user.id != self.organizer.id:

            await interaction.response.send_message(
                "🔒 只有活动组织者可以管理这个活动。",
                ephemeral=True
            )
            return

        if self.cancelled:

            await interaction.response.send_message(
                "这个活动已经取消。",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"⚙️ **管理：{self.activity_name}**\n\n"
            f"正式成员：{len(self.players)} / {self.max_players}\n"
            f"可黑工：{len(self.helpers)} 人",
            view=ManageView(self),
            ephemeral=True
        )


# ============================================================
# TEST COMMAND
# ============================================================

@bot.tree.command(
    name="test",
    description="Check whether WWM Bot is online"
)
async def test(interaction: discord.Interaction):

    await interaction.response.send_message(
        "✅ WWM Party Bot is online!",
        ephemeral=True
    )


# ============================================================
# PARTY COMMAND
# ============================================================

@bot.tree.command(
    name="party",
    description="Create a WWM party recruitment post"
)
@app_commands.describe(
    activity="活动名称，例如：百业十人本",
    time="发车时间，例如：23:00",
    max_players="正式参战人数上限，例如：3 或 10"
)
async def party(
    interaction: discord.Interaction,
    activity: str,
    time: str,
    max_players: app_commands.Range[int, 1, 50]
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "这个命令只能在服务器中使用。",
            ephemeral=True
        )
        return

    view = PartyView(
        activity_name=activity,
        start_time=time,
        max_players=max_players,
        organizer=interaction.user
    )

    await interaction.response.send_message(
        embed=view.build_embed(),
        view=view
    )

    # Store original activity message
    view.message = await interaction.original_response()


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Bot ID: {bot.user.id}")

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
            f"✅ Synced {len(synced)} slash command(s) "
            f"to guild {GUILD_ID}"
        )

        for command in synced:
            print(f"   /{command.name}")

    except Exception as e:

        print(
            f"❌ Failed to sync commands: {e}"
        )


# ============================================================
# START BOT
# ============================================================

bot.run(TOKEN)