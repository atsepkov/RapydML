import os
from util import IndentParser


# close tag flag
NORMAL	= 0
SEPARATE= 1
SINGLE	= 2

def flatten_list(l):
	# takes a list of lists and returns a single list
	return [item for sublist in l for item in sublist]

def uniq(l):
	# remove duplicates from a list
	seen = set()
	seen_add = seen.add
	return [item for item in l if item not in seen and not seen_add(item)]

class LineParser:
	def __init__(self):
		self.attr_stack = []
		self.tree = IndentParser()
	
	def parse_line(self, line):
		# takes a line in '' format and returns key, value pair, where the value is a tuple of flags and an
		# array of allowed attributes
		
		# separate tag and attributes into a list (flattening out any intermediate lists)
		# this will create the following list:
		# ['<tag>', attr1, attr2, attr3]
		key_val = flatten_list([item.strip(',').split(',') for item in line.strip().split()])
		
		# set correct flag and tag
		element = key_val.pop(0)
		modifier = element[-1]
		if modifier == '-':
			flag = SINGLE
			element = element[1:-2]
		elif modifier == '+':
			flag = SEPARATE
			element = element[1:-2]
		else:
			flag = NORMAL
			element = element[1:-1]
		
		# push and pop from the stack as needed
		self.tree.handle_indent(line, [self.attr_stack.pop], [self.attr_stack.append, key_val])
		
		if element == '.':	# meta-node, innacessible to the pyml file
			return None, None
		else:
			attrs = uniq(flatten_list(self.attr_stack))
			if '*' in attrs:
				attrs = None
			return element, (flag, attrs)
		

def load(markup, location=None):
	# take markup and open the relevant file, reading data from it
	# returns a hash of tags and their allowed attributes
	# each entry follows this format:
	#	key	->	([flags], [attrlist])
	#		attrlist is an empty list if no attributes are supported, attrlist is None if any attributes are supported
	
	# convert markup to filename
	if location is None:
		location = os.getcwd()
	filename = os.path.join(location, 'markup', markup)
	
	# start scanning the rules
	buffer = ''
	html_tags = {}
	parser = LineParser()
	with open(filename, 'r') as lang_rules:
		for line in lang_rules:
			
			# remove comments:
			line = line.split('#')[0].rstrip()
			
			# ignore blank lines
			if not line.strip():
				continue
			
			# handle multi-lines
			if buffer:
				line = ' '+line.lstrip()
			if line[-1] == '\\':
				buffer += line[:-1]
			else:
				key, val = parser.parse_line(buffer + line)
				if key is not None:
					try:
						html_tags[key][1].extend(val[1])
					except KeyError:
						html_tags[key] = val
				buffer = ''
	return html_tags
			
