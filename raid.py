import discord

class RaidLFG():
	r_id = 0
	name = ''
	time = 0
	description = ''
	wanters = []
	going = []

	def __init__(self, message, **options):
		super().__init__(**options)
		content = message.content.splitlines()
		self.name = content[1]
		self.time = content[3]
		self.description = content[5]
		self.r_id = message.id
		print(self.r_id)

	def set_id(self, new_id):
		self.r_id = new_id

	def is_raid(self, message):
		print(message.id, self.r_id)
		return message.id == self.r_id
