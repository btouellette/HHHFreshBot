from datetime import datetime, date, timedelta
import OAuth2Util
import praw
import sqlite3
import sys
import time

try:
	import bot
	user = bot.hUser
	version = bot.hUserAgent
	userAgent = bot.hVersion
	subreddit = bot.hSubreddit
	admin = bot.hAdmin
except Exception:
	pass

footer = '\n\n---\n\n^(This post was generated by a bot)\n\n^Subscribe ^to ^roundups: ^[[Daily](http://www.reddit.com/message/compose/?to=HHHFreshBot&subject=subscribe&message=daily)] ^[[Weekly](http://www.reddit.com/message/compose/?to=HHHFreshBot&subject=subscribe&message=weekly)] ^[[Unsubscribe](http://www.reddit.com/message/compose/?to=HHHFreshBot&subject=unsubscribe&message=remove)]\n\n^[[Info](http://www.reddit.com/r/hizinfiz/wiki/HHHFreshBot)] ^[[Source](https://github.com/hizinfiz/HHHFreshBot)] ^[[Feedback](http://www.reddit.com/message/compose/?to=' + admin + '&amp;subject=%2Fu%2FHHHFreshBot%20feedback;message=If%20you%20are%20providing%20feedback%20about%20a%20specific%20post%2C%20please%20include%20the%20link%20to%20that%20post.%20Thanks!)]'

db = sqlite3.connect('fresh.db')
c = db.cursor()
c.execute('CREATE TABLE IF NOT EXISTS subscriptions(USER TEXT, TYPE TEXT)')
db.commit()
db.close()

# Drop last week's table for that day and make a new one
def createDailyTable(day):
	db = sqlite3.connect('fresh.db')
	c = db.cursor()
	# this is to account for the fact that the roundup won't get posted until several hours into Sunday
	if day == 'Sunday':
		c.execute('DROP TABLE IF EXISTS SundayOld')
		c.execute('CREATE TABLE IF NOT EXISTS SundayOld(ID TEXT, TITLE TEXT, PERMA TEXT, URL TEXT, TIME INT, SCORE INT)')
		c.execute('INSERT INTO SundayOld SELECT * FROM Sunday')

	c.execute('DROP TABLE IF EXISTS ' + day)
	c.execute('CREATE TABLE IF NOT EXISTS ' + day + '(ID TEXT, TITLE TEXT, PERMA TEXT, URL TEXT, TIME INT, SCORE INT)')
	db.commit()

# Get all [Fresh] posts, ignoring ones submitted the previous day and ones already added
def getFresh(day, sub):
	thingID = ''
	title = ''
	permalink = ''
	url = ''
	created = ''
	score = 0

	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	for post in sub.get_new(limit=100):
		print('  Looking at post ' + post.id + '...')

		if '[fresh' in post.title.lower():
			print('    Found Fresh!')

			c = db.execute('SELECT * FROM ' + day + ' WHERE ID = ?', (post.id,))

			if c.fetchone() == None:
				thingID = post.id
				title = post.title
				permalink = 'https://redd.it/' + thingID
				url = post.url
				created = post.created_utc
				score = post.score

				if time.strftime("%A", time.gmtime(post.created_utc)) == day:
					param = (thingID, title, permalink, url, created, score)
					db.execute('INSERT INTO ' + day + ' VALUES(?,?,?,?,?,?)', param)
					db.commit()
				else:
					print ('    Wrong Day! D:')
					db.commit()
			else:
				print ('    Skipping :P')
				db.commit()
		
		time.sleep(1)

	c.close()
	db.close()

# Update the scores of logged posts in all tables
def updateScore():
	days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'SundayOld']

	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	for day in days:
		print('  Updating ' + day)
		c.execute('SELECT * FROM ' + day)
		for row in c:
			post = r.get_submission(submission_id = row[0])
			newScore = post.score

			db.execute('UPDATE ' + day + ' SET SCORE = ? WHERE ID = ?', (newScore, row[0]))
			db.commit()

	db.close()

# Delete from the table posts that aren't at +50 after 12 hours
def dropLame(day, yday):
	age = ''

	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	c.execute('SELECT * FROM ' + day)
	for row in c:
		change = time.time() - int(row[4])

		if (change >= 21600) & (row[5] < 25):
			print ('  Deleting ' + row[0])
			db.execute('DELETE FROM ' + day + ' WHERE ID = ?', (row[0],))
			db.commit()

	c.execute('SELECT * FROM ' + yday)
	for row in c:
		change = time.time() - int(row[4])

		if (change >= 21600) & (row[5] < 25):
			print ('  Deleting ' + row[0])
			db.execute('DELETE FROM ' + yday + ' WHERE ID = ?', (row[0],))
			db.commit()

	db.close()

# Checks the inbox for new messages
def checkInbox():
	pms = r.get_unread(update_user=True, limit=1000)
	response = ' '

	for pm in pms:
		try:
			author = pm.author.name
		except:
			pm.mark_as_read()
			continue

		if not pm.was_comment:
			if 'unsubscri' in pm.subject.lower():
				response = unsubscribeUser(author)
			elif 'subscri' in pm.subject.lower():
				if 'daily' in pm.body.lower():
					response = subscribeUser(author, 'daily')
				elif 'weekly' in pm.body.lower():
					response = subscribeUser(author, 'weekly')
				else:
					response = 'I couldn\'t understand this message. Please use one of the links below to subscribe!'
			elif (author == admin) & ('subscri' not in pm.subject.lower()):
				response = 'lol hi'
			else:
				r.send_message(admin, 'PM from /u/' + author, 'Message from /u/' + author + '\n\nSubject: ' + pm.subject + '\n\n---\n\n' + pm.body + footer)
				response = 'I received your message, but I\'m just a bot! I forwarded it to /u/' + admin + ' who will take a look at it when he gets a chance.\n\nIf it\'s urgent, you should PM them directly.\n\nIf you\'re trying to subscribe to one of the roundups, use the links below.\n\nThanks!'

			response += footer

			print ('  Replying to message from ' + author + '...')
			pm.reply(response)
		else:
			r.send_message(admin, 'Comment from /u/' + author, 'Message from /u/' + author + '\n\nSubject: ' + pm.subject + '\n\nContext: ' + pm.context + '\n\n---\n\n' + pm.body)

		pm.mark_as_read()

# Adds users to the table 'subscriptions'
def subscribeUser(user, kind):
	subscription = kind

	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	c = db.execute('SELECT * FROM subscriptions WHERE USER = ?', (user,))

	if c.fetchone() == None:
		db.execute('INSERT INTO subscriptions VALUES(?,?)', [user, subscription])
		db.commit()
		print ('  Adding ' + user + ' to ' + subscription)
		return ('You have been subscribed to the ' + subscription + ' mailing list!')
	else:
		c = db.execute('SELECT * FROM subscriptions WHERE USER = ?', (user,))
		for row in c:
			if row[1] == subscription:
				return ('You are already subscribed to the ' + subscription + ' mailing list!')
			else:
				print ('Adding ' + user + ' to ' + subscription)
				subscription = 'both'
				db.execute('UPDATE subscriptions SET TYPE = ? WHERE USER = ?', [subscription, user])
				db.commit()
				return ('You have been subscribed to both mailing lists!')

	db.close()

# Removes users from the table 'subscriptions'
def unsubscribeUser(user):
	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	c = db.execute('SELECT * FROM subscriptions WHERE USER = ?', (user,))

	if c.fetchone() == None:
		return 'Unable to unsubscribe because you are not currently subscribed to any mailing lists.'
	else:
		print ('  Unsubscribing ' + user + '...')
		db.execute('DELETE FROM subscriptions WHERE USER = ?', (user,))
		db.commit()
		return 'You have been unsubscribed from all mailing lists. Sorry to see you go!'

	db.close()

# Mails out the daily roundup to all daily subscribers
def mailDaily(day):
	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	message = generateDaily(day)
	message[1] += footer
	intro = 'Welcome to The Daily Freshness! Fresh /r/hiphopheads posts delivered right to your inbox each day.\n\n'

	c = db.execute('SELECT * FROM subscriptions WHERE TYPE = ? OR TYPE = ?', ('daily', 'both',))
	for row in c:
		print ('  Mailing ' + row[0] + '...')
		r.send_message(row[0], 'The Daily Freshness for ' + message[0], intro + message[1])

	db.close()

# Creates the roundup for a specific day
def generateDaily(day):
	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	entry = ''
	total = ''
	message = []

	c.execute('SELECT * FROM ' + day)
	datePosted = c.fetchone()[4]
	message.append(time.strftime('%A, %B %d, %Y', time.gmtime(datePosted)))

	c.execute('SELECT * FROM ' + day + ' ORDER BY SCORE DESC')
	for row in c:
		# FORMAT: * [title](permalink) - (+score)
		entry = '* [' + row[1] + '](' + row[2] + ') - (+' + str(row[5]) + ')\n'
		total += entry
	message.append(total)

	db.close()

	return message

# Mails out the weekly round up to all weekly subscribers
def mailWeekly():
	message = generateWeekly()
	body = ''
	intro = 'Welcome to The Weekly Freshness! Fresh /r/hiphopheads posts delivered right to your inbox each day.\n\n'

	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	for mess in message[1:]:
		body += '**' + mess[0] + '**\n\n' + mess[1] + '\n\n'

	body += footer

	c = db.execute('SELECT * FROM subscriptions WHERE TYPE = ? OR TYPE = ?', ('weekly', 'both',))
	for row in c:
		print ('  Mailing ' + row[0] + '...')
		r.send_message(row[0], 'The Weekly Freshness for the week of ' + message[0], intro + body)

	db.close()

# Creates the round up for that week
def generateWeekly():
	days = ['SundayOld', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
	messages = []

	db = sqlite3.connect('fresh.db')
	c = db.cursor()

	c.execute('SELECT * FROM ' + days[0])
	datePosted = c.fetchone()[4]
	messages.append(time.strftime('%A, %B %d, %Y', time.gmtime(datePosted)))

	for day in days:
		messages.append(generateDaily(day))

	db.close()

	return messages

# Unleash the freshness
def submitFreshness():
	message = generateWeekly()
	body = ''
	intro = 'Welcome to The Weekly Freshness! Fresh /r/hiphopheads posts delivered right to your inbox each week.\n\n'

	for mess in message[1:]:
		body += '**' + mess[0] + '**\n\n' + mess[1] + '\n\n'

	body += footer

	r.submit('hizinfiz', 'The Weekly Freshness for the week of ' + message[0], text=intro + body, send_replies=False)

if __name__ == '__main__':
	if not userAgent:
		print("Missing User Agent")
	else:
		print('Logging in...')
		r = praw.Reddit(userAgent + version)
		o = OAuth2Util.OAuth2Util(r)
		o.refresh(force=True)

		sub = r.get_subreddit(subreddit)

		print("Start HHHFreshBot for /r/" + subreddit)

		dayOfWeek = datetime.utcnow().strftime('%A')
		yesterday = (datetime.utcnow() - timedelta(1)).strftime('%A')

	if len(sys.argv) > 1:
		if sys.argv[1] == 'newT':
			print('RUNNING NEWT')
			print('Getting Fresh for ' + yesterday + '...')
			# getFresh(yesterday, sub)
			print('Updating Scores...')
			# updateScore()
			print('Dropping Lame...')
			dropLame(dayOfWeek, yesterday)
			print('Checking Inbox...')
			checkInbox()
			print('Making Table for ' + dayOfWeek + '...')
			createDailyTable(dayOfWeek)
			print('Getting Fresh...')
			getFresh(dayOfWeek, sub)
		elif sys.argv[1] == 'fresh':
			print('RUNNING FRESH')
			print('Getting Fresh for ' + yesterday + '...')
			getFresh(dayOfWeek, sub)
			print('Updating Scores...')
			updateScore()
			print('Dropping Lame...')
			dropLame(dayOfWeek, yesterday)
			print('Checking Inbox...')
			checkInbox()
			print('Done!')
		elif sys.argv[1] == 'mailD':
			print('RUNNING MAILD')
			print('Updating Scores...')
			updateScore()
			print('Dropping Lame...')
			dropLame(dayOfWeek, yesterday)
			print('Checking Inbox...')
			checkInbox()
			print('Mailing Daily for ' + yesterday + '...')
			mailDaily(yesterday)
			print('Done!')
		elif (sys.argv[1] == 'mailW') & (dayOfWeek == 'Sunday'):
			print('RUNNING MAILW')
			print('Updating Scores...')
			updateScore()
			print('Dropping Lame...')
			dropLame(dayOfWeek, yesterday)
			print('Checking Inbox...')
			checkInbox()
			print('Mailing Weekly...')
			mailWeekly()
			print('Submitting Freshness...')
			submitFreshness()
			print('Done!')
		elif sys.argv[1] == 'mailW':
			print('Not Sunday')
		else:
			print('Invalid argument.')

	print("End HHHFreshBot for /r/" + subreddit)
