import discord
from discord.ext import commands, tasks
from discord import app_commands  # works only with py-cord
import os
import random

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# === Game State ===
game_lobby = []
roles = {}
mafia_votes = {}
day_votes = {}
dead_players = []
silenced_players = []
protected_players = set()
doctor_target = None
game_started = False
phase = "day"
vote_timer = 60  # seconds
lovers = set()
duplicated_voters = set()
bodyguard_target = None
bodyguard_last_target = None
vengeful_targets = {}

death_messages = [
    "was found face-first in marinara sauce.",
    "took Big Tony’s parking spot. Bad move.",
    "was last seen asking for pineapple on pizza.",
    "slipped on a cannoli and never got up.",
    "got caught singing to the feds.",
    "forgot the Don’s birthday.",
    "called spaghetti 'noodle soup'.",
    "was too quiet at the meeting.",
    "ate the last cannoli.",
    "thought they could outsmart Big Tony."
]

extended_roles = {
    "Cupid": "Links two lovers. If one dies, the other dies.",
    "Jester": "Wins if voted out during the day.",
    "Foreseer": "Checks alignment at night.",
    "Vengeful Martian": "Kills someone on death.",
    "Duplicated": "Doubles their vote after reveal.",
    "Bodyguard": "Guards one player. Dies instead if that player is attacked.",
    "Friend-zoned Martian": "Silences someone during the day.",
    "Doctor": "Protects one player per night (can be self). Blocks both kills and silencing."
}

@bot.event
async def on_ready():
    print("Big Tony is online.")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
        auto_phase.start()
    except Exception as e:
        print(f"Sync error: {e}")

# === Auto Day/Night Loop ===
@tasks.loop(seconds=vote_timer)
async def auto_phase():
    global phase, doctor_target, bodyguard_target, protected_players
    channel = discord.utils.get(bot.get_all_channels(), name="maafia-game")
    if not game_started or not channel:
        return

    if phase == "day":
        phase = "night"
        if day_votes:
            target = max(day_votes, key=lambda k: len(day_votes[k]))
            if roles.get(target) == "Jester":
                await channel.send(f"{target.display_name} was voted out... and **WINS!**")
            else:
                await channel.send(f"{target.display_name} was voted out. {random.choice(death_messages)}")
                dead_players.append(target)
                if target in lovers:
                    for lover in lovers:
                        if lover != target:
                            await channel.send(f"{lover.display_name} died of heartbreak!")
                            dead_players.append(lover)
        day_votes.clear()
        await channel.send("Night falls. Make your moves.")
    else:
        phase = "day"
        if mafia_votes:
            target = max(mafia_votes, key=lambda k: len(mafia_votes[k]))
            if target in protected_players:
                await channel.send(f"{target.display_name} survived thanks to protection.")
            else:
                await channel.send(f"{target.display_name} was found dead. {random.choice(death_messages)}")
                dead_players.append(target)
                if target in lovers:
                    for lover in lovers:
                        if lover != target:
                            await channel.send(f"{lover.display_name} died of heartbreak!")
                            dead_players.append(lover)
                if roles.get(target) == "Vengeful Martian":
                    revenge = vengeful_targets.get(target)
                    if revenge and revenge not in protected_players:
                        await channel.send(f"{target.display_name} took {revenge.display_name} down with them!")
                        dead_players.append(revenge)
        mafia_votes.clear()
        protected_players.clear()
        doctor_target = None
        await channel.send("The sun rises. Time to vote!")

# === Slash Commands ===
@bot.tree.command(name="join", description="Join the Maafia game.")
async def join(interaction: discord.Interaction):
    if game_started:
        await interaction.response.send_message("Game already started.")
    elif interaction.user in game_lobby:
        await interaction.response.send_message("You're already in.")
    else:
        game_lobby.append(interaction.user)
        await interaction.response.send_message(f"{interaction.user.mention} joined Big Tony’s table.")

@bot.tree.command(name="start", description="Start the game.")
async def start(interaction: discord.Interaction):
    global game_started
    if game_started:
        await interaction.response.send_message("Game already started.")
        return
    if len(game_lobby) < 4:
        await interaction.response.send_message("Need at least 4 players.")
        return
    game_started = True
    pool = list(extended_roles.keys()) + ["Maafia", "Civilian"] * 10
    random.shuffle(game_lobby)
    for i, player in enumerate(game_lobby):
        role = pool[i % len(pool)]
        roles[player] = role
        try:
            await player.send(f"Your role: **{role}**\n{extended_roles.get(role, '')}")
        except:
            await interaction.channel.send(f"Couldn't DM {player.display_name}")
    await interaction.response.send_message("Game started. Roles have been sent!")

@bot.tree.command(name="vote", description="Vote to eliminate someone.")
@app_commands.describe(target="Who you want to vote out")
async def vote(interaction: discord.Interaction, target: discord.Member):
    if phase != "day":
        await interaction.response.send_message("You can only vote during the day.")
        return
    if interaction.user in dead_players:
        await interaction.response.send_message("Ghosts can't vote.")
        return
    day_votes.setdefault(target, set()).add(interaction.user)
    await interaction.response.send_message(f"You voted for {target.display_name}.")

@bot.tree.command(name="whack", description="Mafia vote to kill.")
@app_commands.describe(target="Target to eliminate")
async def whack(interaction: discord.Interaction, target: discord.Member):
    if roles.get(interaction.user) != "Maafia" or phase != "night":
        await interaction.response.send_message("Only Maafia can use this at night.")
        return
    mafia_votes.setdefault(target, set()).add(interaction.user)
    await interaction.response.send_message(f"You voted to whack {target.display_name}.")

@bot.tree.command(name="protect", description="Doctor or Bodyguard protection.")
@app_commands.describe(target="Who to protect")
async def protect(interaction: discord.Interaction, target: discord.Member):
    role = roles.get(interaction.user)
    global bodyguard_target, bodyguard_last_target, doctor_target
    if phase != "night":
        await interaction.response.send_message("Protection only happens at night.")
        return
    if role == "Doctor":
        doctor_target = target
        protected_players.add(target)
        await interaction.response.send_message(f"Doctor is protecting {target.display_name}.")
    elif role == "Bodyguard":
        if target == bodyguard_last_target:
            await interaction.response.send_message("You can’t guard the same person two nights in a row.")
        else:
            bodyguard_last_target = bodyguard_target
            bodyguard_target = target
            protected_players.add(target)
            await interaction.response.send_message(f"Bodyguard is guarding {target.display_name}.")
    else:
        await interaction.response.send_message("You can't protect anyone.")

@bot.tree.command(name="silence", description="Silence a player (Friend-zoned Martian only).")
@app_commands.describe(target="Who to silence")
async def silence(interaction: discord.Interaction, target: discord.Member):
    if roles.get(interaction.user) != "Friend-zoned Martian":
        await interaction.response.send_message("You're not the silencing type.")
        return
    if target == doctor_target:
        await interaction.response.send_message("Silence blocked by Doctor.")
        return
    silenced_players.append(target)
    await interaction.response.send_message(f"{target.display_name} has been silenced.")

@bot.tree.command(name="reveal", description="Foreseer reveals alignment.")
@app_commands.describe(target="Who to check")
async def reveal(interaction: discord.Interaction, target: discord.Member):
    if roles.get(interaction.user) != "Foreseer":
        await interaction.response.send_message("You're not the Foreseer.")
        return
    await interaction.user.send(f"{target.display_name} is a **{roles.get(target)}**.")
    await interaction.response.send_message("Check sent in DMs.")

@bot.tree.command(name="revenge", description="Vengeful Martian sets revenge target.")
@app_commands.describe(target="Who to take down with you")
async def revenge(interaction: discord.Interaction, target: discord.Member):
    if roles.get(interaction.user) != "Vengeful Martian":
        await interaction.response.send_message("You're not a Martian.")
        return
    vengeful_targets[interaction.user] = target
    await interaction.response.send_message(f"You will take {target.display_name} with you if you die.")

@bot.tree.command(name="duplicate", description="Duplicated reveals and gains 2x vote.")
async def duplicate(interaction: discord.Interaction):
    if roles.get(interaction.user) != "Duplicated":
        await interaction.response.send_message("You're not Duplicated.")
        return
    duplicated_voters.add(interaction.user)
    await interaction.response.send_message("You now vote with double strength.")

@bot.tree.command(name="link", description="Cupid links two lovers.")
@app_commands.describe(a="First lover", b="Second lover")
async def link(interaction: discord.Interaction, a: discord.Member, b: discord.Member):
    if roles.get(interaction.user) != "Cupid":
        await interaction.response.send_message("You're not Cupid.")
        return
    global lovers
    lovers = {a, b}
    await interaction.response.send_message(f"{a.display_name} and {b.display_name} are now lovers.")

@bot.tree.command(name="whisper", description="Send a secret DM.")
@app_commands.describe(member="Who to whisper to", message="What to say")
async def whisper(interaction: discord.Interaction, member: discord.Member, message: str):
    if interaction.user in dead_players or member in dead_players:
        await interaction.response.send_message("Ghosts can't whisper.")
        return
    await member.send(f"**Whisper from {interaction.user.display_name}:** {message}")
    await interaction.response.send_message("Message sent.")

@bot.tree.command(name="status", description="Check votes and phase.")
async def status(interaction: discord.Interaction):
    tally = day_votes if phase == "day" else mafia_votes
    vote_display = "\n".join([f"{t.display_name}: {len(v)} vote(s)" for t, v in tally.items()]) or "No votes yet."
    await interaction.response.send_message(f"**Phase:** {phase.title()}\n{vote_display}")

@bot.tree.command(name="help", description="View all bot commands.")
async def help(interaction: discord.Interaction):
    embed = discord.Embed(title="Big Tony Bot Commands", color=0x8B0000)
    for cmd in ["/join", "/start", "/vote", "/whack", "/protect", "/silence", "/reveal",
                "/revenge", "/duplicate", "/link", "/whisper", "/status", "/endgame", "/roles"]:
        embed.add_field(name=cmd, value="Use for gameplay or strategy.", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="roles", description="See role descriptions.")
async def roles(interaction: discord.Interaction):
    embed = discord.Embed(title="Big Tony's Role Guide", color=0xC28840)
    for role, desc in extended_roles.items():
        embed.add_field(name=role, value=desc, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="endgame", description="Reset the game (admin only).")
async def endgame(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can end the game.")
        return
    game_lobby.clear()
    roles.clear()
    mafia_votes.clear()
    day_votes.clear()
    dead_players.clear()
    silenced_players.clear()
    protected_players.clear()
    duplicated_voters.clear()
    lovers.clear()
    vengeful_targets.clear()
    global game_started, phase
    game_started = False
    phase = "day"
    await interaction.response.send_message("Game has been reset.")

bot.run(os.getenv("TOKEN"))
