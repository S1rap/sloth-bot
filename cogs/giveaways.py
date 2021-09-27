import discord
from discord.ext import commands, tasks, flags
from typing import List, Union, Dict, Optional
from random import choice
import os

from extra import utils
from extra.view import GiveawayView
from extra.prompt.menu import Confirm, ConfirmButton

from mysqldb import the_database

server_id = int(os.getenv('SERVER_ID'))
giveaway_manager_role_id: int = int(os.getenv('GIVEAWAY_MANAGER_ROLE_ID'))
mod_role_id = int(os.getenv('MOD_ROLE_ID'))

class Giveaways(commands.Cog):
    """ Category for commands related to giveaways. """

    def __init__(self, client) -> None:
        self.client = client


    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """ Tells when the cog is ready to go. """

        # Makes all registered giveaways consistent
        giveaways = await self.get_giveaways()
        for giveaway in giveaways:
            try:
                self.client.add_view(view=GiveawayView(self.client, giveaway[6]), message_id=giveaway[0])
            except:
                pass

        self.check_old_giveaways.start() # Deletes old giveaways
        self.check_due_giveaways.start() # Checks due giveaways
        print('Giveaways cog is online!')


    @tasks.loop(minutes=1)
    async def check_due_giveaways(self) -> None:
        """ Checks due giveaways and ends them. """


        current_ts = await utils.get_timestamp()
        giveaways = await self.get_due_giveaways(current_ts)
        for giveaway in giveaways:

            if giveaway[5]:
               continue 

            # Gets the channel and message
            channel = message = None
            try:
                channel = await self.client.fetch_channel(giveaway[1])
            except discord.NotFound:
                await self.delete_giveaway(giveaway[0])
                continue
            
            try:
                message = await channel.fetch_message(giveaway[0])
            except discord.NotFound:
                await self.delete_giveaway(giveaway[0])
                continue

            entries = await self.get_giveaway_entries(giveaway[0])

            winners = await self.get_winners(giveaway, entries)

            # Edits the embed
            embed = message.embeds[0]
            embed.title += ' (Ended)'
            embed.color = discord.Color.red()

            view = discord.ui.View.from_message(message)

            await utils.disable_buttons(view)
            await message.edit(embed=embed, view=view)
            # Sends last message
            await message.reply(
                f"**Giveaway is over, we had a total of `{len(entries)}` people participating, and the `{giveaway[3]}` winners are: {winners}!**"
            )
            # Notifies the giveaway's termination
            await self.update_giveaway(giveaway[0])



    @tasks.loop(minutes=1)
    async def check_old_giveaways(self) -> None:
        """ Looks for old giveaways and deletes them.
        
        PS: It looks for giveaways that ended at least 2 days ago. """

        current_ts: int = await utils.get_timestamp()
        await self.delete_old_giveaways(current_ts)

    async def _giveaway_start_callback(
        self, ctx, host: discord.Member, title: str, description: str, prize: str, winners: int = 1, days: int = 0, 
        hours: int = 0, minutes: int = 0, role: discord.Role = None) -> None:
        """ Callback for the giveaway command.
        :param host: The host of the giveaway..
        :param title: Title for the giveaway.
        :param description: Description of giveaway.
        :param prize: Prize giveaway.
        :param winners: Amount of winners. [Optional] [Default = 1]
        :param days: Amount of days until the giveaway ends. [Optional]
        :param hours: Amount of hours until the giveaway ends. [Optional]
        :param minutes: Amount of minutes until the giveaway ends. [Optional]
        :param role: The role for role-only giveaways. [Optional]
        
        PS: The total time summing up days, minutes and minutes MUST be greater than 0. """

        await ctx.defer()

        member = ctx.author
        guild = ctx.guild

        giveaway_time = await self.get_giveaway_time(minutes, hours, days)

        if giveaway_time == 0:
            return await ctx.respond(f"**Please, inform the time, {member.mention}!**", ephemeral=True)

        current_time = await utils.get_time_now()
        current_ts = current_time.timestamp()

        embed = discord.Embed(
            title=f"__{title}__",
            description=description,
            color=member.color,
            timestamp=current_time
        )


        embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)
        embed.set_footer(text=guild.name, icon_url=guild.icon.url)

        deadline_ts = int(current_ts+giveaway_time)

        embed.add_field(
            name="__Info__:",
            value=f"""
            **Hosted by:** {host.mention}
            **Ends:** <t:{deadline_ts}:R>
            **Winners:** {winners}
            **Prize:** {prize}
            **Required Role:** {role.mention if role else None}
            """, inline=False
        )

        try:
            view = GiveawayView(self.client, role.id if role else None)
            msg = await ctx.respond("\u200b", embed=embed, view=view)
            self.client.add_view(view=view, message_id=msg.id)

            await self.insert_giveaway(
                message_id=msg.id, channel_id=msg.channel.id, user_id=host.id, prize=prize,
                winners=winners, deadline_ts=deadline_ts, role_id=role.id if role else None,
            )
        except Exception as e:
            print(e)
            await ctx.respond(f"**Something went wrong with it, {member.mention}!**", ephemeral=True)

    async def _giveaway_list_callback(self, ctx) -> None:
        """ Deletes an existing giveaway. """

        member = ctx.author

        giveaways: List[List[Union[str, int]]] = []

        if await utils.is_allowed([mod_role_id]).predicate(ctx):
            giveaways = await self.get_giveaways()
        else:
            giveaways = await self.get_user_giveaways(member.id)

        if not giveaways:
            return await ctx.respond(f"**You have no active giveaways registered, {member.mention}!**", ephemeral=True)

        message_url = 'https://discord.com/channels/{server_id}/{channel_id}/{message_id}'

        formatted_giveaways: List[str] = '\n'.join([
            f"[Msg]({message_url.format(server_id=server_id, channel_id=ga[1], message_id=ga[0])}) - **P:** `{ga[2]}` **W:** `{ga[3]}` | <t:{ga[4]}:R>"
            for ga in giveaways
        ])

        current_time = await utils.get_time_now()
        embed = discord.Embed(
            title="__Registered Giveaways__",
            description=f"**Msg** = `Message`\n**P** = `Prize`\n**W** = `Winners`\n\n{formatted_giveaways}",
            color=member.color,
            timestamp=current_time
        )

        embed.set_footer(text=f"Requested by: {member}", icon_url=member.display_avatar)

        await ctx.respond(embed=embed, ephemeral=True)

    async def _giveaway_reroll_callback(self, ctx, message_id: int) -> None:
        """ Rerolls a giveaway.
        :param message_id: The ID of the giveaway message. """

        member = ctx.author

        if not message_id:
            return await ctx.respond(f"**Please, inform a message ID, {member.mention}!**", ephemeral=True)

        giveaway = await self.get_giveaway(message_id)
        if not giveaway:
            return await ctx.respond(f"**The specified giveaway doesn't exist, {member.mention}!**", ephemeral=True)

        if giveaway[7] != member.id and not await utils.is_allowed([mod_role_id]).predicate(ctx):
            return await ctx.send(f"**You cannot reroll someone else's giveaway, {member.mention}!**", ephemeral=True)

        if not giveaway[5]:
            return await ctx.respond(f"**This giveaway hasn't ended yet, you can't reroll it, {member.mention}!**", ephemeral=True)

        entries = await self.get_giveaway_entries(giveaway[0])

        winners = await self.get_winners(giveaway, entries)

        # Sends last message
        await ctx.respond(
            f"**Rerolling giveaway with `{len(entries)}` people participating, and the new `{giveaway[3]}` winners are: {winners}!**"
        )

    async def _giveaway_delete_callback(self, ctx, message_id: int) -> None:
        """ Deletes an existing giveaway.
        :param message_id: The ID of the giveaway message. """

        member = ctx.author
        if not message_id:
            return await ctx.respond(f"**Please, inform a message ID, {member.mention}!**", ephemeral=True)

        giveaway = await self.get_giveaway(message_id)
        if not giveaway:
            return await ctx.respond(f"**The specified giveaway message doesn't exist, {member.mention}!**", ephemeral=True)

        if giveaway[7] != member.id and not await utils.is_allowed([mod_role_id]).predicate(ctx):
            return await ctx.send(f"**You cannot delete someone else's giveaway, {member.mention}!**")
            
        confirm_view = ConfirmButton(member, timeout=60)
        embed = discord.Embed(description=f"**Are you sure you wanna delete the giveaway with ID `{giveaway[0]}`, {member.mention}?**", color=member.color)
        await ctx.respond("\u200b", embed=embed, view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value is None:
            return await ctx.respond(f"**{member.mention}, you took too long to answer...**", ephemeral=True)

        if not confirm_view.value:
            return await ctx.respond(f"**Not doing it then, {member.mention}!**", ephemeral=True)

        await self.delete_giveaway(giveaway[0])
        await ctx.respond(f"**Successfully deleted the giveaway with ID: `{giveaway[0]}`, {member.mention}!**", ephemeral=True)
        try:
            channel = discord.utils.get(ctx.guild.text_channels, id=giveaway[1])
            message = await channel.fetch_message(giveaway[0])
            await message.delete()
        except:
            pass

    async def _giveaway_end_callback(self, ctx, message_id: int = None) -> None:
        """ Force-ends an on-going giveaway.
        :param message_id: The ID of the giveaway message. """

        member = ctx.author
        if not message_id:
            return await ctx.respond(f"**Please, inform a message ID, {member.mention}!**", ephemeral=True)

        giveaway = await self.get_giveaway(message_id)
        if not giveaway:
            return await ctx.respond(f"**The specified giveaway message doesn't exist, {member.mention}!**", ephemeral=True)

        if giveaway[5]:
            return await ctx.respond(f"**This giveaway has been ended already, consider using rerolling or deleting it, {member.mention}!**", ephemeral=True)

        confirm_view = ConfirmButton(member, timeout=60)
        embed = discord.Embed(description=f"**Are you sure you want to end the giveaway with ID: `{giveaway[0]}`, {member.mention}?**", color=member.color)
        await ctx.respond("\u200b", embed=embed, view=confirm_view, ephemeral=True)
        await confirm_view.wait()
        if confirm_view.value is None:
            return await ctx.respond(f"**{member.mention}, you took too long to answer...**", ephemeral=True)

        if not confirm_view.value:
            return await ctx.respond(f"**Not doing it then, {member.mention}!**", ephemeral=True)

         # Gets the channel and message
        channel = message = None
        try:
            channel = await self.client.fetch_channel(giveaway[1])
        except discord.errors.NotFound:
            await self.delete_giveaway(giveaway[0])
            return await ctx.respond(f"**Channel of the given giveaway doesn't exist anymore, {member.mention}!**", ephemeral=True)
        
        try:
            message = await channel.fetch_message(giveaway[0])
        except discord.errors.NotFound:
            await self.delete_giveaway(giveaway[0])
            return await ctx.respond(f"**Message of the given giveaway doesn't exist anymore, {member.mention}!**", ephemeral=True)

        try:
            entries = await self.get_giveaway_entries(giveaway[0])
            winners = await self.get_winners(giveaway, entries)

            # Edits the embed
            embed = message.embeds[0]
            embed.title += ' (Ended)'
            embed.color = discord.Color.red()

            view = discord.ui.View.from_message(message)

            await utils.disable_buttons(view)
            await message.edit(embed=embed, view=view)
            # Sends last message
            await message.reply(
                f"**Giveaway is over, we had a total of `{len(entries)}` people participating, and the `{giveaway[3]}` winners are: {winners}!**"
            )
            # Notifies the giveaway's termination
            await self.update_giveaway(giveaway[0])
            current_ts: int = await utils.get_timestamp()
            await self.update_giveaway_deadline(giveaway[0], current_ts)
        except Exception as e:
            print('Error at force-ending giveaway: ', e)
            await ctx.respond(f"**Something went wrong with it, please contact an admin, {member.mention}!**", ephemeral=True)


    async def get_giveaway_time(self, minutes: int, hours: int, days: int) -> int:
        """ Gets the giveaway timeout time in seconds.
        :param minutes: The amount of minutes.
        :param hours: The amount of hours.
        :param dayss: The amount of days. """

        minutes  *= 60
        hours  *= 3600
        days  *= 86400

        return minutes + hours + days


    # Database - Giveaway

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def create_table_giveaways(self, ctx: commands.Context) -> None:
        """ Creates the Giveaways table. """

        member = ctx.author
        await ctx.message.delete()

        if await self.check_giveaways_exists():
            return await ctx.send(f"**Table `Giveaways` already exists, {member.mention}!**")
        
        mycursor, db = await the_database()
        await mycursor.execute("""
            CREATE TABLE Giveaways (
                message_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                prize VARCHAR(100) DEFAULT NULL,
                winners INT DEFAULT 1,
                deadline_ts BIGINT NOT NULL,
                notified TINYINT(1) DEFAULT 0,
                role_id BIGINT DEFAULT NULL,
                user_id BIGINT NOT NULL,
                PRIMARY KEY(message_id)
            )""")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**Table `Giveaways` created, {member.mention}!**")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def drop_table_giveaways(self, ctx: commands.Context) -> None:
        """ Creates the Giveaways table. """

        member = ctx.author
        await ctx.message.delete()

        if not await self.check_giveaways_exists():
            return await ctx.send(f"**Table `Giveaways` doesn't exist, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("DROP TABLE Giveaways")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**Table `Giveaways` dropped, {member.mention}!**")


    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def reset_table_giveaways(self, ctx: commands.Context) -> None:
        """ Creates the Giveaways table. """

        member = ctx.author
        await ctx.message.delete()

        if not await self.check_giveaways_exists():
            return await ctx.send(f"**Table `Giveaways` doesn't exist yet, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("DELETE FROM Giveaways")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**Table `Giveaways` reset, {member.mention}!**")

    async def check_giveaways_exists(self) -> bool:
        """ Checks whether the Giveaways table exists. """

        mycursor, _ = await the_database()
        await mycursor.execute("SHOW TABLE STATUS LIKE 'Giveaways'")
        exists = await mycursor.fetchone()
        await mycursor.close()
        if exists:
            return True
        else:
            return False


    async def insert_giveaway(
        self, message_id: int, channel_id: int, user_id: int, 
        prize: str, winners: int, deadline_ts: int, role_id: Optional[int] = None) -> None:
        """ Inserts a giveaway.
        :param message_id: The ID of the message in which the giveaway is attached to.
        :param channel_id: The ID of the channel in which the giveaway is made.
        :param prize: The prize of the giveaway.
        :param winners: The amount of winners for the giveaway.
        :param deadline_ts: The deadline timestamp of the giveaway.
        :param role_id: The ID of the role for role-only giveaways. [Optional] """

        mycursor, db = await the_database()
        await mycursor.execute("""
            INSERT INTO Giveaways (message_id, channel_id, prize, winners, deadline_ts, role_id, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""", (
                message_id, channel_id, prize, winners, deadline_ts, role_id, user_id))
        await db.commit()
        await mycursor.close()

    async def get_giveaways(self) -> List[List[Union[str, int]]]:
        """ Gets all active giveaways. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM Giveaways")
        giveaways = await mycursor.fetchall()
        await mycursor.close()
        return giveaways

    async def get_user_giveaways(self, user_id: int) -> List[List[Union[str, int]]]:
        """ Gets all active giveaways from a specific user.
        :param user_id: The ID of the user to get giveaways from. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM Giveaways WHERE user_id = %s", (user_id,))
        giveaways = await mycursor.fetchall()
        await mycursor.close()
        return giveaways

    async def get_giveaway(self, message_id: int) -> List[Union[str, int]]:
        """ Gets a specific active giveaways.
        :param message_id: The ID of the message in which the giveaway is attached to. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM Giveaways WHERE message_id =  %s", (message_id,))
        giveaway = await mycursor.fetchone()
        await mycursor.close()
        return giveaway

    async def get_due_giveaways(self, current_ts: int) -> List[List[Union[str, int]]]:
        """ Gets due giveaways.
        :param current_ts: The current timestamp to compare to registered giveaways' timestamps. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM Giveaways WHERE deadline_ts <= %s AND notified = 0", (current_ts,))
        giveaways = await mycursor.fetchall()
        await mycursor.close()
        return giveaways

    async def update_giveaway(self, message_id: int, notified: Optional[int] = 1) -> None:
        """ Updates the giveaway's notified status.
        :param message_id: The ID of the message of the giveaway.
        :param notified: If it's gonna be set to true or false. [Optional][Default = 1 = True] """

        mycursor, db = await the_database()
        await mycursor.execute("UPDATE Giveaways SET notified = %s WHERE message_id = %s", (notified, message_id))
        await db.commit()
        await mycursor.close()

    async def update_giveaway_deadline(self, message_id: int, current_ts: int) -> None:
        """ Updates the giveaway's deadline timestamp..
        :param message_id: The ID of the message of the giveaway.
        :param current_ts: The current timestamp. """

        mycursor, db = await the_database()
        await mycursor.execute("UPDATE Giveaways SET deadline_ts = %s WHERE message_id = %s", (current_ts, message_id))
        await db.commit()
        await mycursor.close()


    async def delete_giveaway(self, message_id: int) -> None:
        """ Deletes a giveaway.
        :param message_id: The ID of the message in which the giveaway is attached to. """

        mycursor, db = await the_database()
        await mycursor.execute("DELETE FROM Giveaways WHERE message_id = %s", (message_id,))
        await db.commit()
        await mycursor.close()

    async def delete_old_giveaways(self, current_ts: int) -> None:
        """ Deletes old ended giveaways of at least 2 days ago. """

        mycursor, db = await the_database()
        await mycursor.execute("""
            DELETE FROM Giveaways WHERE notified = 1 AND %s - deadline_ts >= 172800""", (current_ts,))
        await db.commit()
        await mycursor.close()

    # Database - GiveawayEntries
    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def create_table_giveaway_entries(self, ctx: commands.Context) -> None:
        """ Creates the GiveawayEntries table. """

        member = ctx.author
        await ctx.message.delete()

        if await self.check_giveaway_entries_exists():
            return await ctx.send(f"**Table `GiveawayEntries` already exists, {member.mention}!**")
        
        mycursor, db = await the_database()
        await mycursor.execute("""
            CREATE TABLE GiveawayEntries (
                user_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                PRIMARY KEY (user_id, message_id),
                CONSTRAINT fk_ga_msg_id FOREIGN KEY (message_id) REFERENCES Giveaways (message_id) ON UPDATE CASCADE ON DELETE CASCADE
            )""")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**Table `GiveawayEntries` created, {member.mention}!**")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def drop_table_giveaway_entries(self, ctx: commands.Context) -> None:
        """ Creates the GiveawayEntries table. """

        member = ctx.author
        await ctx.message.delete()

        if not await self.check_giveaway_entries_exists():
            return await ctx.send(f"**Table `GiveawayEntries` doesn't exist, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("DROP TABLE GiveawayEntries")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**Table `GiveawayEntries` dropped, {member.mention}!**")


    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def reset_table_giveaway_entries(self, ctx: commands.Context) -> None:
        """ Creates the GiveawayEntries table. """

        member = ctx.author
        await ctx.message.delete()

        if not await self.check_giveaway_entries_exists():
            return await ctx.send(f"**Table `GiveawayEntries` doesn't exist yet, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("DELETE FROM GiveawayEntries")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**Table `GiveawayEntries` reset, {member.mention}!**")

    async def check_giveaway_entries_exists(self) -> bool:
        """ Checks whether the GiveawayEntries table exists. """

        mycursor, _ = await the_database()
        await mycursor.execute("SHOW TABLE STATUS LIKE 'GiveawayEntries'")
        exists = await mycursor.fetchone()
        await mycursor.close()
        if exists:
            return True
        else:
            return False

    async def insert_giveaway_entry(self, user_id: int, message_id: int) -> None:
        """ Inserts an entry for an active giveaway.
        :param user_id: The ID of the user who's participating in the giveaway.
        :param message_id: The ID of the message of the giveaway the user is participating in. """

        mycursor, db = await the_database()
        await mycursor.execute("INSERT INTO GiveawayEntries (user_id, message_id) VALUES (%s, %s)", (user_id, message_id))
        await db.commit()
        await mycursor.close()


    async def get_giveaway_entry(self, user_id: int, message_id: int) -> List[Union[str, int]]:
        """ Gets a specific entry from an active giveaway.
        :param user_id: The ID of the user to get.
        :param message_id: The ID of the message of the giveaway. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM GiveawayEntries WHERE user_id = %s AND message_id = %s", (user_id, message_id))
        entry = await mycursor.fetchone()
        await mycursor.close()
        return entry

    async def get_giveaway_entries(self, message_id: int) -> List[List[Union[str, int]]]:
        """ Gets all entries from an active giveaway.
        :param message_id: The ID of the message of the giveaway. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM GiveawayEntries WHERE message_id = %s", (message_id,))
        entries = await mycursor.fetchall()
        await mycursor.close()
        return entries

    async def delete_giveaway_entry(self, user_id: int, message_id: int) -> None:
        """ Deletes an entry from an active giveaway.
        :param user_id: The ID of the user who was participating in the giveaway.
        :param message_id: The ID of the message of the giveaway the user was participating in. """

        mycursor, db = await the_database()
        await mycursor.execute("DELETE FROM GiveawayEntries WHERE user_id = %s AND message_id = %s", (user_id, message_id))
        await db.commit()
        await mycursor.close()

    async def get_winners(self, giveaway: List[Union[str, int]], entries: List[List[Union[str, int]]]) -> str:
        """ Gets text-formatted winners from giveaways.
        :param giveaway: The giveaway to get the winners from. """

        if not entries:
            return 'No one, since there were no entries in this giveaway'

        amount_of_winners = giveaway[3]

        winners = []

        while True:
            winner = choice(entries)
            # Checks whether winner is not in the list yet
            if winner not in winners:
                winners.append(winner)

            # Checks whether it sorted the required amount of winners
            if len(winners) == amount_of_winners:
                break

            # Checks whether there are enough entries to sort more winners
            if len(entries) < amount_of_winners:
                break

        return ', '.join([f"<@{w[0]}>" for w in winners])


    
"""
Setup:

z!create_table_giveaways
z!create_table_giveaway_entries
"""



def setup(client) -> None:
    client.add_cog(Giveaways(client))