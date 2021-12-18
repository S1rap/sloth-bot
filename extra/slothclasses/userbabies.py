import discord
from discord.ext import commands
from mysqldb import the_database
from typing import List, Union, Optional


class UserBabiesTable(commands.Cog):
    """ Class for the UserBabies table and its commands and methods. """

    def __init__(self, client: commands.Bot) -> None:
        """ Class init method. """

        self.client = client

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def create_table_user_babies(self, ctx) -> None:
        """ Creates the UserBabies table in the database. """

        member: discord.Member = ctx.author
        if await self.check_user_babies_table_exists():
            return await ctx.send(f"**The UserBabies table already exists, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("""CREATE TABLE UserBabies (
            parent_one BIGINT NOT NULL,
            parent_two BIGINT NOT NULL,
            baby_name VARCHAR(25) DEFAULT 'Embryo',
            baby_class VARCHAR(25) DEFAULT 'Embryo',
            life_points TINYINT(3) DEFAULT 100,
            food TINYINT(3) DEFAULT 100,
            PRIMARY KEY (parent_one, parent_two)
            ) CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci
        """)
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**`UserBabies` table created, {member.mention}!**")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def drop_table_user_babies(self, ctx) -> None:
        """ Drops the UserBabies table from the database. """

        member: discord.Member = ctx.author
        if not await self.check_user_babies_table_exists():
            return await ctx.send(f"**The UserBabies table doesn't exist, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("DROP TABLE UserBabies")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**`UserBabies` table dropped, {member.mention}!**")

    @commands.command(hidden=True)
    @commands.has_permissions(administrator=True)
    async def reset_table_user_babies(self, ctx) -> None:
        """ Resets the UserBabies table in the database. """

        member: discord.Member = ctx.author
        if not await self.check_user_babies_table_exists():
            return await ctx.send(f"**The UserBabies table doesn't exist yet, {member.mention}!**")

        mycursor, db = await the_database()
        await mycursor.execute("DELETE FROM UserBabies")
        await db.commit()
        await mycursor.close()

        await ctx.send(f"**`UserBabies` table reset, {member.mention}!**")

    async def check_user_babies_table_exists(self) -> bool:
        """ Checks whether the UserBabies table exists in the database. """

        mycursor, _ = await the_database()
        await mycursor.execute("SHOW TABLE STATUS LIKE 'UserBabies'")
        exists = await mycursor.fetchone()
        await mycursor.close()
        if exists:
            return True
        else:
            return False

    async def insert_user_baby(self, parent_one: int, parent_two: int, baby_name: Optional[str] = None, baby_class: Optional[str] = None) -> None:
        """ Inserts a User Baby.
        :param parent_one: The parent one of the baby.
        :param parent_two: The parent two of the baby.
        :param baby_name: The name of the baby. [Optional]
        :param baby_class: The class of the baby. [Optional]"""

        mycursor, db = await the_database()
        if baby_name and baby_class:
            await mycursor.execute("""
                INSERT INTO UserBabies (parent_one, parent_two, baby_name, baby_class) VALUES (%s, %s, %s, %s)
                """, (parent_one, parent_two, baby_name, baby_class))
        else:
            await mycursor.execute("INSERT INTO UserBabies (user_id, parent_one, parent_two) VALUES (%s, %s)", (parent_one, parent_two))
        await db.commit()
        await mycursor.close()

    async def get_user_baby(self, parent_id: int) -> List[Union[str, int]]:
        """ Get the user's baby.
        :param parent_id: The ID of one of the baby's parents. """

        mycursor, _ = await the_database()
        await mycursor.execute("SELECT * FROM UserBabies WHERE parent_one = %s OR parent_two = %s", (parent_id, parent_id))
        user_baby = await mycursor.fetchone()
        await mycursor.close()
        return user_baby

    async def update_user_baby_name(self, parent_id: int, baby_name: str) -> None:
        """ Updates the User Baby's name.
        :param parent_id: The ID of one of the baby's parents.
        :param baby_name: The new baby name to update to. """

        mycursor, db = await the_database()
        await mycursor.execute("UPDATE UserBabies SET baby_name = %s WHERE parent_one = %s OR parent_two = %s", (baby_name, parent_id, parent_id))
        await db.commit()
        await mycursor.close()

    async def update_user_baby_class(self, parent_id: int, baby_class: str) -> None:
        """ Updates the User Baby's class.
        :param parent_id: The ID of one of the the baby's parents.
        :param baby_class: The new baby class to update to. """

        mycursor, db = await the_database()
        await mycursor.execute("UPDATE UserBabies SET baby_class = %s WHERE parent_one = %s OR parent_two = %s", (baby_class, parent_id, parent_id))
        await db.commit()
        await mycursor.close()

    async def update_user_baby_lp(self, parent_id: int, increment: int = 5) -> None:
        """ Updates the User Baby's life points.
        :param parent_id: The ID of one of the baby's parents.
        :param increment: The incremention value to apply. [Default = 5] (Can be negative) """

        mycursor, db = await the_database()
        await mycursor.execute("UPDATE UserBabies SET life_points = life_points + %s WHERE parent_one = %s OR parent_two = %s", (increment, parent_id, parent_id))
        await db.commit()
        await mycursor.close()

    async def update_user_baby_food(self, parent_id: int, increment: int = 5) -> None:
        """ Updates the User Baby's food status.
        :param parent_id: The ID of one of the baby's parents.
        :param increment: The incremention value to apply. [Default = 5] (Can be negative) """

        mycursor, db = await the_database()
        await mycursor.execute("UPDATE UserBabies SET food = food + %s WHERE parent_one = %s OR parent_two = %s", (increment, parent_id, parent_id))
        await db.commit()
        await mycursor.close()

    async def delete_user_baby(self, parent_id: int) -> None:
        """ Deletes the user's baby.
        :param parent_id: The ID of one of the baby's parents. """

        mycursor, db = await the_database()
        await mycursor.execute("DELETE FROM UserBabies WHERE parent_one = %s or parent_two = %s", (parent_id, parent_id))
        await db.commit()
        await mycursor.close()

