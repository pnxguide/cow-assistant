import discord
import sqlite3
import json

config_file = open("config.json")
config = json.load(config_file)

bot = discord.Bot(intents=discord.Intents.all())
con = sqlite3.connect(config["DATABASE_FILE_PATH"])

@bot.event
async def on_ready():
    print(f"{bot.user} is ready and online!")

BASELINE = 0.5
MASTER = 0.9

def get_class(scores):
    master_count = 0
    baseline_count = 0

    lt = scores

    for l in lt:
        if l[1] > BASELINE:
            baseline_count += 1
        if l[1] > MASTER:
            master_count += 1
    
    if master_count == 4 and baseline_count == 4:
        return "Grand Master (A)"
    elif master_count == 3 and baseline_count == 4:
        return "Master (A)"
    elif master_count == 2 and baseline_count == 4:
        return "Expert (B+)"
    elif master_count == 1 and baseline_count == 4:
        return "Specialist (B)"
    elif baseline_count == 4:
        return "Apprentice+ (C+)"
    elif baseline_count == 3:
        return "Apprentice (C)"
    elif baseline_count == 2:
        return "Rookie+ (D+)"
    elif baseline_count == 1:
        return "Rookie (D)"
    else:
        return "Underclass (F)"

def percent_to_blocks(percent: float, color: int):
    MAX_BLOCKS = 20
    num_blocks = int(percent * MAX_BLOCKS)
    grey_blocks = MAX_BLOCKS - num_blocks

    block_str = ""

    COLORS = ["🟩", "🟦", "🟥", "🟪", "🟧", "🟨", "⬛"]

    if percent >= MASTER:
        color = len(COLORS) - 2
    elif percent < BASELINE:
        color = len(COLORS) - 1
        
    for i in range(num_blocks):
        block_str = block_str + COLORS[color]

    for i in range(grey_blocks):
        block_str = block_str + "⬜"

    return block_str

def is_registered(discord_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT COUNT(*) FROM students WHERE discord_id = ?", (int(discord_id), ))
    count = int(res.fetchone()[0])
    cur.close()
    return count == 1

def get_pairs():
    pairs = []
    cur = con.cursor()
    cur.execute("SELECT student1, student2 FROM pairs WHERE is_assignment = 0")

    for row in cur:
        pairs.append((row[0], row[1]))

    cur.close()

    return pairs

def get_nickname(discord_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT nickname FROM students WHERE discord_id = ?", (int(discord_id), ))
    nickname = res.fetchone()[0]
    cur.close()
    return nickname

def get_scores_by_id(discord_id: int):
    scores = []

    cur = con.cursor()
    cur.execute("""
        WITH skill_set_cte AS (
            SELECT skill_set, SUM(max_score) AS score
            FROM assignments
            GROUP BY skill_set
        )
        SELECT assignments.skill_set, skill_set_types.skill_set_name, COALESCE(SUM(score) / (SELECT skill_set_cte.score FROM skill_set_cte WHERE skill_set_cte.skill_set = assignments.skill_set LIMIT 1), 0)
        FROM submissions
            RIGHT JOIN assignments ON submissions.assignment_id = assignments.assignment_id AND student_id = (SELECT student_id FROM students WHERE discord_id = ?)
            JOIN skill_set_types ON skill_set_types.skill_set_id = assignments.skill_set
        GROUP BY assignments.skill_set, skill_set_types.skill_set_name
        ORDER BY assignments.skill_set
    """, (int(discord_id), ))
    
    for row in cur:
        scores.append((row[1], float(row[2])))

    cur.close()

    return scores

def get_schedules():
    schedules = []

    cur = con.cursor()
    cur.execute("""
        SELECT date, time_slot * 15 / 60 AS start_hour, substr('00'||(time_slot * 15 % 60), -2) AS start_minute,
            (time_slot + 1) * 15 / 60 AS end_hour, substr('00'||((time_slot + 1) * 15 % 60), -2) AS end_minute,
            COALESCE(ts.student_id, -1), COALESCE(p.student1, -1), COALESCE(p.student2, -1)
        FROM timeslots AS ts
            LEFT JOIN pairs AS p ON ts.student_id = p.student1 OR ts.student_id = p.student2
        WHERE date > DATE('now', '+7 hour');
    """)
    
    for row in cur:
        a = set()
        a.add(int(row[5]))
        a.add(int(row[6]))
        a.add(int(row[7]))
        schedules.append((f"{row[0]} {row[1]}:{row[2]} - {row[3]}:{row[4]}", a))

    cur.close()
    return schedules

def get_point_by_id(discord_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT points FROM students WHERE discord_id = ? LIMIT 1", (int(discord_id), ))
    points = res.fetchone()[0]
    cur.close()
    return points

def get_late_day_by_id(discord_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT grace_days - (SELECT SUM(late_day_used) FROM submissions WHERE submissions.student_id = students.student_id) FROM students WHERE discord_id = ? LIMIT 1", (int(discord_id), ))
    points = res.fetchone()[0]
    cur.close()
    return points

def get_point_by_student_id(student_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT points FROM students WHERE student_id = ? LIMIT 1", (int(student_id), ))
    points = res.fetchone()[0]
    cur.close()
    return points

def get_assignment_name_by_id(assignment_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT assignment_name FROM assignments WHERE assignment_id = ? LIMIT 1", (int(assignment_id), ))
    assignment_name = res.fetchone()[0]
    cur.close()
    return assignment_name

def get_discord_id_by_student_id(student_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT discord_id FROM students WHERE student_id = ? LIMIT 1", (int(student_id), ))
    discord_id = res.fetchone()[0]
    cur.close()
    return discord_id

def get_student_id_by_discord_id(discord_id: int):
    cur = con.cursor()
    res = cur.execute("SELECT student_id FROM students WHERE discord_id = ? LIMIT 1", (int(discord_id), ))
    student_id = res.fetchone()[0]
    cur.close()
    return student_id

async def add_point_by_student_id(student_id: int, point_to_add: int, reason: str, client):
    cur = con.cursor()
    cur.execute("UPDATE students SET points = points + ? WHERE student_id = ?", (int(point_to_add), int(student_id), ))
    cur.close()
    con.commit()
    
    # Notify student
    discord_id = get_discord_id_by_student_id(student_id)
    user = client.get_user(int(discord_id))
    await user.send(f"**[ONE-Stamp Update]** You got {point_to_add} ONE-Stamp(s)!\n\n(Reason: {reason})\n")

def register(discord_id: int, student_id: int, passcode: str, nickname: str):
    cur = con.cursor()
    res = cur.execute("SELECT COALESCE(passcode, 'wtf') FROM students WHERE student_id = ?", (int(student_id), ))
    actual_passcode = res.fetchone()[0]
    cur.close()

    if actual_passcode == passcode:
        if not is_registered(discord_id):
            cur = con.cursor()
            cur.execute("UPDATE students SET discord_id = ?, nickname = ? WHERE student_id = ?", (int(discord_id), nickname, int(student_id), ))
            cur.close()
            con.commit()
        else:
            return "ALREADY_REGISTERED"
    else:
        return "PASSCODE_MISMATCHED"

    return "SUCCESS"

def get_score_breakdown(discord_id: int):
    scores = []

    cur = con.cursor()
    cur.execute("""
        SELECT assignments.assignment_id, assignments.assignment_name, COALESCE(submissions.score, 0), assignments.max_score, COALESCE(submissions.score / assignments.max_score, 0) AS percent
        FROM submissions
            JOIN assignments ON submissions.assignment_id = assignments.assignment_id
        WHERE submissions.student_id = (SELECT student_id FROM students WHERE discord_id = ?);
    """, (int(discord_id), ))
    
    for row in cur:
        scores.append((row[0], row[1], float(row[2]), float(row[3]), float(row[4])))

    cur.close()

    return scores

def get_skill_set():
    skill_sets = []

    cur = con.cursor()
    cur.execute("""
        SELECT skill_set_id, skill_set_name
        FROM skill_set_types
    """, ())
    
    for row in cur:
        skill_sets.append((row[0], row[1]))

    cur.close()

    return skill_sets

def get_available_slots(date, hour):
    slots = []

    cur = con.cursor()
    cur.execute("""
        SELECT timeslot_id, substr('00'||(time_slot * 15 % 60), -2) AS minute 
        FROM timeslots WHERE student_id IS NULL AND date = ? AND time_slot * 15 / 60 = ?;
    """, (date, hour, ))
    
    for row in cur:
        slots.append((row[0], row[1]))

    cur.close()

    return slots

def get_available_hours(date):
    hours = []

    cur = con.cursor()
    cur.execute("""
        SELECT DISTINCT time_slot * 15 / 60 AS hour FROM timeslots WHERE student_id IS NULL AND date = ?;
    """, (date,))
    
    for row in cur:
        hours.append(row[0])

    cur.close()

    return hours

def get_available_dates():
    dates = []

    cur = con.cursor()
    cur.execute("""
        SELECT DISTINCT date FROM timeslots WHERE student_id IS NULL AND date > DATE('now', '+7 hour');
    """, ())
    
    for row in cur:
        dates.append(row[0])

    cur.close()

    return dates

def get_current_schedule(discord_id: int):
    schedule = ""

    cur = con.cursor()
    res = cur.execute("""
        SELECT timeslot_id, date, 
            time_slot * 15 / 60 AS start_hour, substr('00'||(time_slot * 15 % 60), -2) AS start_minute,
            (time_slot + 1) * 15 / 60 AS end_hour, substr('00'||((time_slot + 1) * 15 % 60), -2) AS end_minute,
            student_id, COALESCE(p1.student2, COALESCE(p2.student1, -1)),
            (SELECT assignment_name FROM assignments WHERE assignment_id = assignment)
        FROM timeslots
            LEFT JOIN pairs AS p1 ON 
                p1.student1 = student_id
            LEFT JOIN pairs AS p2 ON 
                p2.student2 = student_id
        WHERE (student_id = (SELECT student_id FROM students WHERE discord_id = ?) OR
            (p1.student2 = (SELECT student_id FROM students WHERE discord_id = ?) OR p2.student1 = (SELECT student_id FROM students WHERE discord_id = ?))) AND
            assignment = 302
    """, (discord_id, discord_id, discord_id, ))
    
    result = res.fetchone()
    cur.close()

    if result:
        timeslot_id, date, start_hour, start_minute, end_hour, end_minute, pair1, pair2, assignment = result
        if pair2 == -1:
            return (f"{date} {start_hour}:{start_minute}", f"{date} {end_hour}:{end_minute}", [pair1], assignment, timeslot_id)
        else:
            return (f"{date} {start_hour}:{start_minute}", f"{date} {end_hour}:{end_minute}", [pair1, pair2], assignment, timeslot_id)

    return -1

def get_assignments_by_skill_set(skill_set_id: int, discord_id: int):
    assignments = []

    cur = con.cursor()
    cur.execute("""
        SELECT assignments.assignment_id, assignments.assignment_name, COALESCE(submissions.submission_id, -1)
        FROM assignments
            LEFT JOIN submissions ON submissions.assignment_id = assignments.assignment_id AND submissions.student_id = (SELECT student_id FROM students WHERE discord_id = ?)
        WHERE assignments.skill_set = ?
    """, (discord_id, skill_set_id, ))
    
    for row in cur:
        assignments.append((row[0], row[1], row[2]))

    cur.close()

    return assignments

def get_submission_detail(submission_id):
    cur = con.cursor()
    res = cur.execute("""
        SELECT submissions.submission_id, assignments.assignment_name, COALESCE(submissions.score, 0), assignments.max_score, COALESCE(submissions.score / assignments.max_score, 0) AS percent, submissions.feedback, submissions.late_day_used
        FROM submissions
            INNER JOIN assignments ON submissions.assignment_id = assignments.assignment_id
        WHERE submissions.submission_id = ?
    """, (submission_id, ))
    submission_id, assignment_name, score, max_score, percent, feedback, late_day_used = res.fetchone()
    cur.close()
    return (submission_id, assignment_name, score, max_score, percent, feedback, late_day_used)

class PersistentView(discord.ui.View):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.timeout = None

class RegistrationModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="What is your student ID?"))
        self.add_item(discord.ui.InputText(label="What is your secret code?"))
        self.add_item(discord.ui.InputText(label="What should we call you?", max_length=16))

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Registration")

        student_id = self.children[0].value
        passcode = self.children[1].value
        nickname = self.children[2].value

        status = "FAILED"
        if len(nickname) > 16:
            status = "NICKNAME_TOO_LONG"
        else:
            status = register(interaction.user.id, student_id, passcode, nickname)

        if status == "SUCCESS":
            embed.description = "The registration is successful. Please try checking your status."
        elif status == "NICKNAME_TOO_LONG":
            embed.description = "Your nickname is too long (more than 16 characters). Please try again."
        elif status == "ALREADY_REGISTERED":
            embed.description = "This Student ID has already been registered. If you think that this is wrong, please contact course staff."
        else:
            embed.description = "The registration is failed. Your passcode maybe wrong. Please try again."

        await interaction.response.send_message(embeds=[embed])

class RegistrationPage(discord.ui.View):
    @discord.ui.button(label="Register", row=0, style=discord.ButtonStyle.primary, emoji="✍️")
    async def register_callback(self, button, interaction):
        await interaction.response.send_modal(RegistrationModal(title="Registration"))

def feedback_callback(submission_id: int):
    async def callback(interaction):
        submission_detail = get_submission_detail(submission_id)
        embed = discord.Embed(title="Assignment Report")
        embed.add_field(name="Assignment Name", value=str(submission_detail[1]), inline=False)
        embed.add_field(name="Score", value=f"{submission_detail[2]}/{submission_detail[3]} ({round(submission_detail[4]*100, 2)}%)", inline=False)
        embed.add_field(name="Grace Day(s) Used", value=str(submission_detail[6]), inline=False)
        embed.add_field(name="Feedback", value=str(submission_detail[5].replace("\\n", "\n")), inline=False)
        await interaction.response.send_message(embeds=[embed])
    return callback

class ReportPerAssignmentPage(discord.ui.View):
    def __init__(self, skill_set_id, user_id):
        super().__init__()
        assignments = get_assignments_by_skill_set(skill_set_id, user_id)
        for assignment in assignments:
            is_disabled = (assignment[2] == -1)
            button = discord.ui.Button(label=f"{assignment[1]}", disabled=is_disabled)
            button.callback = feedback_callback(assignment[2])
            self.add_item(button)

def skill_callback(data):
    async def callback(interaction):
        await interaction.response.defer()
        await interaction.user.send("Please choose the assignment you want to view", view=ReportPerAssignmentPage(int(data[0]), interaction.user.id))
    return callback

class ReportPage(discord.ui.View):
    def __init__(self):
        super().__init__()
        skill_set_types = get_skill_set()
        for skill_set in skill_set_types:
            button = discord.ui.Button(label=f"{skill_set[1]}")
            button.callback = skill_callback(skill_set)
            self.add_item(button)

def schedule_timeslot(discord_id, timeslot_id):
    cur = con.cursor()
    cur.execute("""
        UPDATE timeslots
        SET student_id = (SELECT student_id FROM students WHERE discord_id = ?)
        WHERE timeslot_id = ? AND student_id IS NULL
    """, (discord_id, timeslot_id, ))
    cur.close()
    con.commit()

def cancel_schedule(timeslot_id):
    cur = con.cursor()
    cur.execute("""
        UPDATE timeslots
        SET student_id = NULL
        WHERE timeslot_id = ?
    """, (timeslot_id, ))
    cur.close()
    con.commit()

def confirmX_callback(data):
    async def callback(interaction):
        await interaction.response.defer()
        # A. Update the slot
        schedule_timeslot(interaction.user.id, data)

        # B. Send the notification to all
        current_schedule = get_current_schedule(interaction.user.id)
        
        if current_schedule == -1:
            await interaction.user.send("The time slot has not been successfully scheduled. Please try again.")
        else:
            embed = discord.Embed(title="Check-Out Appointed")
            embed.add_field(name="Assignment Name", value=str(current_schedule[3]), inline=False)
            embed.add_field(name="Start Date/Time", value=str(current_schedule[0]), inline=False)
            embed.add_field(name="End Date/Time", value=str(current_schedule[1]), inline=False)
            participant_str = ""
            for part in current_schedule[2]:
                participant_str += f"{part}\n"
            embed.add_field(name="Partipants", value=participant_str, inline=False)

            for part in current_schedule[2]:
                participant_str += f"{part}\n"

            # Notify student
            for part in current_schedule[2]:
                discord_id = get_discord_id_by_student_id(part)
                user = interaction.client.get_user(int(discord_id))
                await user.send(embeds=[embed])

    return callback

class TimeSlotPickerPage(discord.ui.View):
    def __init__(self, date, hour):
        super().__init__()
        self.timeout = 15
        slots = get_available_slots(date, hour)
        for slot in slots:
            button = discord.ui.Button(label=f"{date} {hour}:{slot[1]}")
            button.callback = confirmX_callback(slot[0])
            self.add_item(button)

def hour_callback(data):
    async def callback(interaction):
        await interaction.response.defer()
        await interaction.user.send("Please choose your preferred slot\n(Warning: it will proceed immediately.)", view=TimeSlotPickerPage(data[0], int(data[1])))
    return callback

class HourPickerPage(discord.ui.View):
    def __init__(self, date):
        super().__init__()
        self.timeout = 15
        hours = get_available_hours(date)
        for hour in hours:
            button = discord.ui.Button(label=f"{hour}")
            button.callback = hour_callback((date, hour))
            self.add_item(button)

def date_callback(data):
    async def callback(interaction):
        await interaction.response.defer()
        await interaction.user.send("Please choose your preferred hour", view=HourPickerPage(data))
    return callback

class DatePickerPage(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.timeout = 15
        dates = get_available_dates()
        for date in dates:
            button = discord.ui.Button(label=f"{date}")
            button.callback = date_callback(date)
            self.add_item(button)

class ScheduleCancellationPage(discord.ui.View):
    def __init__(self, timeslot_id: int):
        super().__init__()
        self.timeslot_id = timeslot_id
        self.add_item(discord.ui.Button(label='Link to Meeting (Currently, on Discord)', disabled=True))

    @discord.ui.button(label="Cancel Appointment", row=0, style=discord.ButtonStyle.danger)
    async def cancel_callback(self, button, interaction):
        await interaction.response.defer()
        cancel_schedule(self.timeslot_id)
        await interaction.user.send("The cancellation is complete. You can re-schedule the new appointment.")

class DiscoveryPage(discord.ui.View):
    @discord.ui.button(label="View Current Status", row=0, style=discord.ButtonStyle.primary, emoji="⚡")
    async def current_status_callback(self, button, interaction):
        embed = discord.Embed(title="Current Status")
        if is_registered(interaction.user.id):
            embed.description = f"Hello {get_nickname(interaction.user.id)}! Here is your current status..."

            point = get_point_by_id(interaction.user.id)
            scores = get_scores_by_id(interaction.user.id)
            cur_late_day = get_late_day_by_id(interaction.user.id)
            cur_class = get_class(scores)

            embed.add_field(name="Class", value=cur_class, inline=False)
            embed.add_field(name="ONE-Stamp", value=str(point), inline=True)
            embed.add_field(name="Grace Day(s) Left", value=str(cur_late_day), inline=True)

            for i in range(len(scores)):
                embed.add_field(name=f"Skill Set #{i+1}: {scores[i][0]} ({round(scores[i][1] * 100, 2)}%)", value=percent_to_blocks(scores[i][1], i), inline=False)
        else:
            embed.description = "You have not yet registered. Please register before you check the status!"
        await interaction.response.send_message(embeds=[embed])

    @discord.ui.button(label="View Score Breakdown", row=0, style=discord.ButtonStyle.primary, emoji="📊")
    async def breakdown_callback(self, button, interaction):
        embed = discord.Embed(title="Score Breakdown")
        if is_registered(interaction.user.id):
            scores = get_score_breakdown(interaction.user.id)
            description = ""
            for score in scores:
                description += f"{score[1]}: {score[2]}/{score[3]} ({round(score[4] * 100, 2)}%)\n"
            embed.description = description
        else:
            embed.description = "You have not yet registered. Please register before you check the status!"
        await interaction.response.send_message(embeds=[embed])

    @discord.ui.button(label="View Assignment Report", row=0, style=discord.ButtonStyle.primary, emoji="📘")
    async def assignment_callback(self, button, interaction):
        await interaction.response.defer()
        await interaction.user.send("Please choose one of the following skill sets", view=ReportPage())

    @discord.ui.button(label="View Inventory", row=0, style=discord.ButtonStyle.primary, emoji="📦", disabled=True)
    async def inventory_callback(self, button, interaction):
        pass

    @discord.ui.button(label="Assignment Pair Up", row=1, style=discord.ButtonStyle.secondary, disabled=True)
    async def assignment_pair_callback(self, button, interaction):
        pair = get_pair(interaction.user.id, "assignment")
        if pair == None:
            await interaction.response.send_modal(PairSignUpModal(title="Pairing Up for Assignments", type="assignment"))
        else:
            await interaction.response.defer()
            if is_waiting_for_confirmation(interaction.user.id, "assignment"):
                await interaction.user.send("You have elected to pair up OR you are the chosen one. Please wait for your pick or confirm/deny the prior request.")
            else:
                await interaction.user.send(f"{pair} is now your awesome companion for the programming assignment from now on. If you want to make change, please contact the staff.")

    @discord.ui.button(label="Assignment Check-Out", row=1, style=discord.ButtonStyle.secondary, disabled=True)
    async def checkout_callback(self, button, interaction):
        current_schedule = get_current_schedule(interaction.user.id)
        if current_schedule == -1:
            await interaction.response.defer()
            await interaction.user.send("Please choose your preferred date", view=DatePickerPage())
        else:
            embed = discord.Embed(title="Check-Out Schedule")
            embed.add_field(name="Assignment Name", value=str(current_schedule[3]), inline=False)
            embed.add_field(name="Start Date/Time", value=str(current_schedule[0]), inline=False)
            embed.add_field(name="End Date/Time", value=str(current_schedule[1]), inline=False)

            participant_str = ""
            for part in current_schedule[2]:
                participant_str += f"{part}\n"
            embed.add_field(name="Partipants", value=participant_str, inline=False)

            await interaction.response.send_message(embeds=[embed], view=ScheduleCancellationPage(current_schedule[4]))
    
    @discord.ui.button(label="Project Sign-Up", row=1, style=discord.ButtonStyle.secondary, disabled=True)
    async def project_pair_callback(self, button, interaction):
        pair = get_pair(interaction.user.id, "project")
        if pair == None:
            await interaction.response.send_modal(PairSignUpModal(title="Pairing Up for the Project", type="project"))
        else:
            await interaction.response.defer()
            if is_waiting_for_confirmation(interaction.user.id, "project"):
                await interaction.user.send("You have elected to pair up OR you are the chosen one. Please wait for your pick or confirm/deny the prior request.")
            else:
                await interaction.user.send(f"{pair} is now your awesome companion for the programming assignment from now on. If you want to make change, please contact the staff.")

def get_pair(discord_id: int, type: str):
    cur = con.cursor()
    if type == "assignment":
        res = cur.execute("""
            SELECT
                CASE
                    WHEN student1 = (SELECT student_id FROM students WHERE discord_id = ?) THEN student2
                    ELSE student1
                END
            FROM pairs
            WHERE (student1 = (SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 1;
        """, (discord_id, discord_id, discord_id, ))
    elif type == "project":
        res = cur.execute("""
            SELECT
                CASE
                    WHEN student1 = (SELECT student_id FROM students WHERE discord_id = ?) THEN student2
                    ELSE student1
                END
            FROM pairs
            WHERE (student1 = (SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 0;
        """, (discord_id, discord_id, discord_id, ))

    result = res.fetchone()
    cur.close()

    if result == None:
        return None

    return result[0]

def is_waiting_for_confirmation(discord_id: int, type: str):
    cur = con.cursor()
    if type == "assignment":
        res = cur.execute("""
            SELECT
                is_confirmed
            FROM pairs
            WHERE (student1 = (SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 1;
        """, (discord_id, discord_id, ))
    elif type == "project":
        res = cur.execute("""
            SELECT
                is_confirmed
            FROM pairs
            WHERE (student1 = (SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 0;
        """, (discord_id, discord_id, ))

    result = res.fetchone()
    cur.close()

    if result == None:
        return False

    is_confirmed = result[0]
    return (is_confirmed == 0)

def pair_sign_up(id1: int, id2: int, type: str):
    id1tmp = min(id1, id2)
    id2tmp = max(id1, id2)
    id1 = id1tmp
    id2 = id2tmp
    cur = con.cursor()
    if type == "assignment":
        cur.execute("""
            INSERT INTO pairs (student1, student2, is_confirmed, is_assignment)
            VALUES ((SELECT student_id FROM students WHERE discord_id = ?), (SELECT student_id FROM students WHERE discord_id = ?), 0, 1);
        """, (int(id1), int(id2), ))
    elif type == "project":
        cur.execute("""
            INSERT INTO pairs (student1, student2, is_confirmed, is_assignment)
            VALUES ((SELECT student_id FROM students WHERE discord_id = ?), (SELECT student_id FROM students WHERE discord_id = ?), 0, 0);
        """, (int(id1), int(id2), ))
    cur.close()
    con.commit()

def confirm_pair(discord_id: int, type: str):
    cur = con.cursor()
    if type == "assignment":
        cur.execute("""
            UPDATE pairs
            SET is_confirmed = 1
            WHERE ((SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 1;
        """, (discord_id, discord_id, ))
    elif type == "project":
        cur.execute("""
            UPDATE pairs
            SET is_confirmed = 1
            WHERE ((SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 0;
        """, (discord_id, discord_id, ))
    cur.close()
    con.commit()

def remove_pair(discord_id: int, type: str):
    cur = con.cursor()
    if type == "assignment":
        cur.execute("""
            DELETE FROM pairs
            WHERE ((SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 1;
        """, (discord_id, discord_id, ))
    elif type == "project":
        cur.execute("""
            DELETE FROM pairs
            WHERE ((SELECT student_id FROM students WHERE discord_id = ?) OR student2 = (SELECT student_id FROM students WHERE discord_id = ?)) AND
                is_assignment = 0;
        """, (discord_id, discord_id, ))
    cur.close()
    con.commit()

class PairSignUpConfirmationPage(PersistentView):
    def __init__(self, type: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = type

    @discord.ui.button(label="Confirm", row=0, style=discord.ButtonStyle.primary)
    async def confirm_callback(self, button, interaction):
        confirm_pair(interaction.user.id, self.type)
        await interaction.response.defer()
        await interaction.user.send("You just confirmed this pair up request. Congrats!")

        pair_id = get_pair(interaction.user.id, self.type)
        pair_discord_id = get_discord_id_by_student_id(pair_id)
        user = interaction.client.get_user(int(pair_discord_id))
        await user.send("Your pair just confirmed the pair up request. Congrats!")
    
    @discord.ui.button(label="Deny", row=0, style=discord.ButtonStyle.danger)
    async def deny_callback(self, button, interaction):
        pair_id = get_pair(interaction.user.id, self.type)
        pair_discord_id = get_discord_id_by_student_id(pair_id)
        user = interaction.client.get_user(int(pair_discord_id))
        await user.send("Your pair just denied the pair up request. Please try again.")

        remove_pair(interaction.user.id, "assignment")
        await interaction.response.defer()
        await interaction.user.send("You just denied this pair-up request.")

class PairSignUpModal(discord.ui.Modal):
    def __init__(self, type: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.type = type
        self.add_item(discord.ui.InputText(label="Your Pair Student ID"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pair_id = int(self.children[0].value)
        pair_discord_id = get_discord_id_by_student_id(pair_id)
        pair = get_pair(pair_discord_id, self.type)
        if pair == None:
            pair_sign_up(interaction.user.id, pair_discord_id, self.type)
            user = interaction.client.get_user(int(pair_discord_id))
            await user.send(f"Student {get_student_id_by_discord_id(interaction.user.id)} has elected to pair up with you.", view=PairSignUpConfirmationPage(self.type))
            await interaction.followup.send("Please wait for your pair to confirm this aggrement.")
        else:
            if is_waiting_for_confirmation(interaction.user.id, self.type):
                await interaction.user.send("Your pick is now waiting for the other's confirmation. Please try again.")
            else:
                await interaction.followup.send("The student ID you picked has already got a pair. Please try again.")

class MenuBar(PersistentView):
    def __init__(self):
        super().__init__()
        self.add_item(discord.ui.Button(label='Assignment Submission', style=discord.ButtonStyle.url, url='https://classroom.google.com/c/NzI5NTc3MjQwMjY0?cjc=fqinlng'))
        self.add_item(discord.ui.Button(label='Course Schedule', style=discord.ButtonStyle.url, url='https://pnx.guide/course/2024/05696110/schedule.html'))
        self.add_item(discord.ui.Button(label='Course Material', style=discord.ButtonStyle.url, url='https://drive.google.com/drive/folders/1lFEQqrV1elo5HoOXqvJDh0xOoGSpc5JV'))
        self.add_item(discord.ui.Button(label='Course Webpage', style=discord.ButtonStyle.url, url='https://pnx.guide/course/2024/05696110/'))

    @discord.ui.button(label="Talk to Cow", row=1, style=discord.ButtonStyle.primary, emoji="💬")
    async def talk_callback(self, button, interaction):
        await interaction.response.defer()
        if is_registered(interaction.user.id):
            await interaction.user.send("Please choose one of the following options", view=DiscoveryPage())
        else:
            await interaction.user.send("Please register by hitting the following button", view=RegistrationPage())

@bot.slash_command()
async def menu(ctx):
    await ctx.respond(view=MenuBar())

class AddModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Student ID"))
        self.add_item(discord.ui.InputText(label="Point Change (- for deducting points)"))

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Point Update")

        student_id = self.children[0].value
        points = int(self.children[1].value)

        await add_point_by_student_id(student_id, points, "-", interaction.client)
        embed.description = f"The current balance of {student_id} is {get_point_by_student_id(student_id)}."

        await interaction.response.send_message(embeds=[embed])

class CheckModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Student ID"))

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Point Update")
        student_id = self.children[0].value
        embed.description = f"The current balance of {student_id} is {get_point_by_student_id(student_id)}."
        await interaction.response.send_message(embeds=[embed])

async def update_score(assignment_id: int, csv: str, client):
    lines = csv.splitlines()
    tuple_list = []
    for line in lines:
        escaped_line = line.replace("\,", ";w;")
        id, score, feedback, late_day_used = escaped_line.split(",")
        feedback = feedback.replace(";w;", ",")
        tuple_list.append((int(id), float(score), str(feedback), int(late_day_used)))

    assignment_name = get_assignment_name_by_id(assignment_id)
    
    result = ""
    for tp in tuple_list:
        id, score, feedback, late_day_used = tp
        cur = con.cursor()
        cur.execute("""
            INSERT INTO submissions (student_id, assignment_id, score, feedback, late_day_used) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(student_id, assignment_id) DO UPDATE SET score = ?, feedback = ?, late_day_used = ?;
        """, (int(id), int(assignment_id), float(score), feedback, int(late_day_used), float(score), feedback, int(late_day_used), ))
        cur.close()
        con.commit()

        result += f"Assign {score} to {id} with {late_day_used} late days\n"

        # Notify student
        discord_id = get_discord_id_by_student_id(id)
        user = client.get_user(int(discord_id))
        await user.send(f"Your score and the feedback for {assignment_name} are ready for you to view.\n")

    return result

class BulkGradeModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Assignment ID"))
        self.add_item(discord.ui.InputText(label="Student ID, Score, Feedback, Late Day", style=discord.InputTextStyle.long))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        assignment_id = int(self.children[0].value)
        ids_and_scores = self.children[1].value

        embed = discord.Embed(title=f"Grade Assignment {assignment_id}")
        embed.description = await update_score(assignment_id, ids_and_scores, interaction.client)
        await interaction.followup.send(embeds=[embed])

class BulkAddModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Student ID", style=discord.InputTextStyle.long))
        self.add_item(discord.ui.InputText(label="Point Change"))
        self.add_item(discord.ui.InputText(label="Reason"))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        student_ids = self.children[0].value.replace(",", "\n").splitlines()
        point = int(self.children[1].value)
        reason = self.children[2].value

        description = ""

        for student_id in student_ids:
            await add_point_by_student_id(student_id, point, reason, interaction.client)
            description += f"The current balance of {student_id} is {get_point_by_student_id(student_id)}.\n"

        embed = discord.Embed(title="Point Update")
        embed.description = description
        await interaction.followup.send(embeds=[embed])

class AdminMenuBar(PersistentView):
    @discord.ui.button(label="Check Point")
    async def check_point_callback(self, button, interaction):
        await interaction.response.send_modal(CheckModal(title="Check Point"))

    @discord.ui.button(label="Update Point")
    async def update_point_callback(self, button, interaction):
        await interaction.response.send_modal(AddModal(title="Update Point"))

    @discord.ui.button(label="Bulk Update Point")
    async def bulk_update_point_callback(self, button, interaction):
        await interaction.response.send_modal(BulkAddModal(title="Bulk Point Update", timeout=None))

    @discord.ui.button(label="Bulk Grade")
    async def grade_callback(self, button, interaction):
        await interaction.response.send_modal(BulkGradeModal(title="Bulk Grade", timeout=None))

    @discord.ui.button(label="List Schedules")
    async def schedule_callback(self, button, interaction):
        schedules = get_schedules()
        text = "Schedule\n"
        for schedule in schedules:
            text += f"{schedule[0]} |"
            for student in schedule[1]:
                text += f" {student}"
            text += "\n"
        await interaction.response.send_message(text)
    
    @discord.ui.button(label="List Assignment Pairs")
    async def pair_callback(self, button, interaction):
        pairs = get_pairs()
        text = ""
        for index, pair in enumerate(pairs):
            text += f"Project Pair #{index+1}: {pair[0]}, {pair[1]}\n"
        await interaction.response.send_message(text)

@bot.slash_command()
async def admin(ctx):
    print(ctx.author.id)
    if ctx.author.id == int(config["ADMIN_DISCORD_ID"]):
        await ctx.respond(view=AdminMenuBar())
    else:
        await ctx.send("You do not have permission to use this command.")

if __name__ == '__main__':
    try:
        bot.run(config["DISCORD_TOKEN"])
    except KeyboardInterrupt:
        con.close()
