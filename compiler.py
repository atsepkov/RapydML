import sys, re
import string
from util import IndentParser, ParserError
from markuploader import NORMAL, SINGLE

def is_number(s):
	try:
		float(s)
		return True
	except ValueError:
		return False

def is_valid_name(s):
	# returns true if name follows Pythonic standard
	return not not re.match('^[a-zA-Z_][a-zA-Z0-9]*$', s)

def expand_arrays(tag):
	# expands shorthand arrays such as [1:5] into full-array [1,2,3,4,5]
	# [0:6] 	-> [0,1,2,3,4,5,6]
	# [1:8:2]	-> [1,3,5,7]
	# [8:1:-1]	-> [8,7,6,5,4,3,2,1]
	# [8:1]		-> []
	matches = re.findall('(\[(-?\d+):(-?\d+)(:(-?\d+))*\])', tag)
	for array in matches:
		if array[-1] == '':
			increment = 1
		else:
			increment = int(array[-1])
		if increment > 0:
			final = int(array[2])+1
		else:
			final = int(array[2])-1
		tag = tag.replace(array[0], str(range(int(array[1]),final,increment)))
	return tag
	
attr_map = {'.' : 'class'}
def convert_attr(attr):
	# converts attribute CSS-like shorthands to proper HTML
	attr = attr.strip()
	if attr[0] in attr_map.keys():
		return '%s="%s"' % (attr_map[attr[0]], attr[1:])
	elif attr.find('=') != -1 and is_number(attr.split('=')[1]):
		pair = attr.split('=')
		return '%s="%s"' % (pair[0].strip(), pair[1].strip())
	else:
		return attr

def get_attr(tag):
	# retrieves all attributes in a given function call/definition tag
	# this logic respects commas inside a string
	attr_string = re.findall(r'\((.*)\)', tag)[0]
	if attr_string == '':
		return []
	else:
		attr_list = attr_string.split(',')
		
		buffer = ''
		in_string = False
		in_list = False
		final_attr_list = []
		for attr in attr_list:
			attr = attr.strip()
			if in_string or in_list:
				buffer += ','+attr
			else:
				buffer = attr
			
			if attr.count('"') % 2 or attr.count("'") % 2:
				in_string = not in_string
			
			if attr[0] == '[':
				in_list = True
			if attr[-1] == ']':
				in_list = False
			
			if not in_string and not in_list:
				final_attr_list.append(buffer.strip())
		
		for i in range(len(final_attr_list)):
			final_attr_list[i] = convert_attr(final_attr_list[i])
			if final_attr_list[i][0] in ('"', "'") \
			and re.match(r'(["\'])[^"\']+\1\s*=.*', final_attr_list[i]):
				# strip quotes from attribute name (because attr names with special chars
				# require quotes, i.e. 'z-index'
				final_attr_list[i] = final_attr_list[i].replace(final_attr_list[i][0], '', 2)
		return final_attr_list
	
def parse_definition(tag):
	# parses DOM element or function definition
	tag = tag.strip()
	if tag.find('(') != -1:
		element = tag.split('(')[0].rstrip()
		attributes = get_attr(tag)
	else:
		element = tag.replace(':', '')
		attributes = []
	return element, attributes
		
def replace_variables(code, var_hash, ignore_list=[]):
	#plugs the variables into the line
	vars = re.findall('(?<!\\\\)\$[A-Za-z_][A-Za-z0-9_]*', code)
	
	for var in ignore_list:
		try:
			vars.remove(var)
		except ValueError:
			pass # variable doesn't appear on this line
	
	for var in vars:
		try:
			# the first version will not replace 2nd occurence in strings like '$a$a'
			#code = re.sub('(?<!(\\\\|[A-Za-z0-9_]))\%s(?![A-Za-z0-9_])' % var, var_hash[var], code)
			code = re.sub('(?<!\\\\)\%s(?![A-Za-z0-9_])' % var, var_hash[var], code)
		except KeyError:
			raise ParserError("Variable %s used prior to definition" % var)
			
	return code

def expand_assignment(tag):
	# handles expansion of increment logic
	result = tag.split('+=')[0].split('-=')[0].split('*=')[0].split('/=')[0].strip()
	tag = tag.replace('+=', ':= %s + (' % result)\
			.replace('-=', ':= %s - (' % result)\
			.replace('*=', ':= %s * (' % result)\
			.replace('/=', ':= %s / (' % result)
	if tag.count('(') > tag.count(')'):
		tag = tag.rstrip() + ')\n'
	return result, tag

def do_arithmetic(operation):
	# this function solves simple arithmetic such as +/-/*//
	# if we detect # or non-numeric variable, that's not a method, try to run it through color converter
	# valid color formats we expect are '#ffffff', '#000', or 'white' (note the quotes, we assume them necessary)
	# what about style?
	try:
		result = eval(operation)
		return repr(result)
	except SyntaxError, NameError:
		raise ParserError("Command '%s' is not a valid mathematical operation" % operation.strip())

def parse_array_part(array_part):
	# helper method for scanning the passed in string backwards and returning a corresponding array
	# it ignores whatever is to the left of the array
	array = []
	start_index = 0
	buffer = ''
	brackets = 0
	in_single_quote = False
	in_double_quote = False
	for index in range(len(array_part))[::-1]:
		if array_part[index] == ']' and not in_single_quote and not in_double_quote:
			brackets += 1
			if brackets > 1:
				buffer = array_part[index] + buffer
		elif array_part[index] == '[' and not in_single_quote and not in_double_quote:
			brackets -= 1
			if brackets >= 1:
				buffer = array_part[index] + buffer
		elif array_part[index] == '"' and not in_single_quote and array_part[index-1] != '\\':
			in_double_quote = not in_double_quote
			buffer = array_part[index] + buffer
		elif array_part[index] == "'" and not in_double_quote and array_part[index-1] != '\\':
			in_single_quote = not in_single_quote
			buffer = array_part[index] + buffer
		elif array_part[index] == ',' and not in_single_quote and not in_double_quote and brackets == 1:
			array.append(buffer.strip())
			buffer = ''
		else:
			buffer = array_part[index] + buffer
		
		if brackets == 0:
			if buffer:
				array.append(buffer.strip())
			start_index = index
			break
	array.reverse()
	return array, start_index

def parse_template_engine_method_declaration(line):
	command_pair = line.split('=', 1)
	if len(command_pair) != 2:
		raise ParserError("Improper TemplateEngine method declaration, variable assigned to must follow format of TemplateEngine.MethodName")
	method_pair = command_pair[0].rstrip().rsplit('.', 1)
	method, attributes = parse_definition(command_pair[1])
	return method_pair[0], method_pair[1], method, attributes

def create_tag(element, attributes):
	attr_string = ' '.join(attributes)
	if attr_string:
		starttag = '<%s %s>\n' % (element, attr_string)
	else:
		starttag = '<%s>\n' % element
	endtag = '</%s>\n' % element
	return starttag, endtag

class ColorConverter:
	"""
	Helper class for handling color conversion, so that we can perform math operations on it
	"""

	def __init__(self):
		# create a map for html color names
		self.color_map = {}
		with open('html_colors.txt', 'r') as input:
			for line in input:
				pair = line.split(':')
				self.color_map[pair[0]] = pair[1].rstrip()
	
	def is_color(self, color_string):
		return color_string in self.color_map.keys()
	
	def to_num(self, color):
		# first we standardize colors to 6-digit hex format
		color = color.lower()
		if color in self.color_map.keys():
			color = self.color_map[color]
		elif len(color) == 3:
			color = '%s%s%s%s%s%s' % (color[0], color[0], color[1], color[1], color[2], color[2])
		elif len(color) != 6:
			raise ParserError("Color '%s' is not a valid HTML color" % color)
		
		# now we return base 10 representation of the number
		return int(color, 16)
	
	def to_color(self, num):
		return hex(num)[2:].zfill(6)
	
class Method:
	"""
	Helper class for generating html-creating methods
	"""
	
	def __init__(self, attributes, copy_heap, color_parser):
		# create a new method that can be invoked later
		# attributes: set of parameters this method will take in (this will be defined at function invocation)
		# heap: the memory space this method sees
		#	can be used to hide some vaiables from a method or 'shadow' global variables by passing copies
		self.attributes = attributes
		self.lines = []
		self.color = color_parser
		self.copy_heap = copy_heap
	
	def add_line(self, line):
		# this is where we handle replacing predefined variables
		trash, line = expand_assignment(line)
		self.lines.append(line)
	
	def eval_chunk(self, part):
		if re.search('[-+*/](?=(?:(?:[^"]*"){2})*[^"]*$)', part) and \
		re.search("[-+*/](?=(?:(?:[^']*'){2})*[^']*$)", part):
			
			# check for potential colors:
			# check for "blue" etc
			# check for #fff etc
			is_color_computation = False
			possible_colors = re.findall('"[A-Za-z]+"(?=(?:(?:[^"]*"){2})*[^"]*$)', part)
			possible_hex_colors = re.findall('#[A-Fa-f0-9]+(?=(?:(?:[^"]*"){2})*[^"]*$)', part)
			for color in possible_colors:
				color = color[1:-1]
				if self.color.is_color(color):
					is_color_computation = True
					part = re.sub('"%s"' % color, str(self.color.to_num(color)), part)
			for color in possible_hex_colors:
				if len(color) == 4 or len(color) == 7:
					is_color_computation = True
					part = re.sub('%s' % color, str(self.color.to_num(color[1:])), part)
			
			part = do_arithmetic(part)
			if is_color_computation:
				part = max(min(int(part), 0xffffff), 0x000000)
				part = '#%s' % self.color.to_color(part)
		return part
	
	def eval_line(self, line):
		# returns evaluated version of the line
		line = replace_variables(line, self.heap)
		#TEMP: this tester is naive, it assumes the strings will not contain ' or " characters inside of them
		#BUG: we need to resolve things like div(#tag-id,#f00+#001)
		if re.search('^[A-Za-z_][A-Za-z0-9_]*[ ]*\(.*\)', line.strip()):
			whitespace = line.split(line.strip()[0])[0]
			element, attributes = parse_definition(line)
			for i in range(len(attributes)):
				attributes[i] = self.eval_chunk(attributes[i])
			return '%s%s(%s)' % (whitespace, element, ','.join(attributes))
		else:
			line = self.eval_chunk(line)
		return line
	
	def run_method(self, args, heap):
		if self.copy_heap:
			self.heap = heap.copy()
		else:
			self.heap = heap
		#var_hash = {} #if we 'clutter' the global heap, it makes some logic easier and allows more Python-like reuse of variables after loop terminates
		for i in range(len(self.attributes)):
			#TEMP: the \ replacing is a temporary quickfix for misunderstood problem of Python interpreting the string when it shouldn't
			#var_hash[self.attributes[i]] = args[i].replace('\\','\\\\')
			self.heap[self.attributes[i]] = args[i].replace('\\','\\\\')
		for line in self.lines:
			# this is where we handle replacing method arguments
			assignments = line.count(':=')
			if assignments == 1:
				operands = line.split(':=')
				self.heap[operands[0].strip()] = self.eval_line(operands[1].strip())
				yield None # this line produces no output
			elif assignments > 1:
				raise "Multiple assignments on same line aren't allowed"
			else:
				yield self.eval_line(line)
			
			#yield replace_variables(line, var_hash)

class TemplateEngine:
	"""
	Helper class for generating HTML templates used by various templating engines such as Django,
	web2py, or Rails
	"""
	
	def __init__(self, tag_format):
		# tag_format must include brackets and have %s for location of internal logic
		self.tag_format = tag_format + '\n'
		self.methods = {}
		self.method_stack = []
	
	def handle_indent(self, indent, method_name):
		# push to or pop from the stack, depending on indent
		
		# first method call
		if self.method_stack:
			indent_diff = indent-self.method_stack[-1][1]
		else:
			self.method_stack.append((method_name, indent))
			return
			
		if self.is_submethod(method_name, indent): #indent_diff == 0 and method_name in self.methods[self.method_stack[-1][0]][3]:
			# this is a submethod of current method
			#self.method_stack.append((self.method_stack[-1][0], indent))
			pass
		elif indent_diff < 1: #pop
			while indent_diff < 1:
				self.method_stack.pop()
				indent_diff += 1
			self.method_stack.append((method_name, indent))
		elif indent_diff > 1:
			raise ParserError('Incorrect indentation')
	
	def add_method(self, name, start_format, end_format=None):
		# add a method we can call later
		num_vars = start_format.count('%s')
		submethods = []
		self.methods[name] = (start_format, num_vars, end_format, submethods)
	
	def enhance_method(self, original_method, sub_method):
		# allows submethod to be assosciated with existing method, preventing the end_method from getting triggered
		self.methods[original_method][3].append(sub_method)
	
	def is_submethod(self, method_name, indent):
		# returns true if method_name is a submethod of previously invoked method
		return self.method_stack and method_name in self.methods[self.method_stack[-1][0]][3] and indent == self.method_stack[-1][1]
	
	def call_method(self, method, vars, indent):
		# this returns an actual template tag to use for this method call
		if len(vars) != self.methods[method][1]:
			raise ParserError("TemplateEngine method %s takes %d variables, %d given" % (method, self.methods[method][1], len(vars)))
		
		self.handle_indent(indent, method)
		vars = tuple(vars)
		contents = self.methods[method][0] % vars
		return self.tag_format % contents
	
	def end_method(self, method, close=True):
		# return the end method for 
		if close and self.method_stack:
			self.method_stack.pop()
		if self.methods[method][2] is None:
			return None
		else:
			return self.tag_format % self.methods[method][2]

class Parser:
	"""
	Usage:
	html = Parser()
	with open(output_file, 'w') as output:
		output.write(html.parse(input_file))
	"""
	reserved_internal_methods = [
		'create',
		'append',
		'verbatim',
		'verbatim_line'
	]
	
	def __init__(self, valid_tags):
		self.valid_tags = valid_tags
		self.tree = IndentParser()
		self.element_stack = []
		self.output = ''
		self.last_opened_element = None
		self.var_map = {}
		
		self.creating_method = None
		self.method_map = {}
		self.loop_stack = []
		self.loop_index = 0
		
		self.template_engines = {}
		self.color = ColorConverter()
		self.imported_files = []
		
		self.verbatim = {}
		self.current_verbatim = None
		self.verbatim_indent = 0
		self.verbatim_buffer = ''
	
	def write(self, line, overlap = 0):
		# helper method for writing to file, all writes should be done through it to ensure a single point
		# of entry
		line = line.replace('\$', '$')
		if overlap != 0:
			self.output = self.output[:overlap] + line
		else:
			self.output += line
	
	def resolve_indexes(self, line):
		# replace all indexes with corresponding values
		while line.count(']['):
			try:
				parts = line.split('][')
				array, start_index = parse_array_part(parts[0]+']')
				index = parts[1].split(']')[0]	#this can trigger IndexError
				num = int(index)				#this can trigger ValueError
				line = line.replace(line[start_index:len('%s[%s]' % (parts[0],index))+1], array[num])
			except ValueError:
				# this occurs if we try something like array['abcd'] or array[3.5]
				raise ParserError("Invalid index '%s', index must be an integer" % index)
			except IndexError:
				# this occurs if we try some improperly terminated line like array[ or ][
				raise ParserError("Syntax error while trying to parse index")
		
		return line
	
	def close_last_element(self):
		# closes last html tag
		tag = self.element_stack.pop()
			
		if tag is None:
			return # this is not an element that requires closing
		
		# in order to use short-hand <tag /> we need to make sure that tag is not a special tag, 
		# and that the name matches as well as indent
		if self.last_opened_element is None:
			tag_type = -1
		else:
			try:
				tag_type = self.valid_tags[self.last_opened_element][0]
			except KeyError:
				# WE SHOULD NOT GET IN HERE UNLESS SOMETHING IS WRONG
				try:
					tag_type = self.valid_tags['*'][0]
				except KeyError:
					print "This logic should not trigger, please inform RapydML developers, provide the contents of your .pyml file as well."
					raise ParserError("'%s' is not a valid markup tag or method name." % self.last_opened_element)
		
		if tag_type == NORMAL \
		and re.search('^%s</%s>' % (self.tree.indent_marker*self.tree.indent, self.last_opened_element), tag):
			self.write(' />\n', -2)
		elif tag_type != SINGLE or self.last_opened_element is None:
			self.write(tag)
				
	
	def set_variable(self, tag):
		# sets the variable(s) in the system
		vars = tag.split(':=')
		if len(vars) == 1:
			raise ParserError("You're trying to declare variable %s without assignment" % vars[0].strip())
			
		text = vars[-1].lstrip()
		for var in vars[:-1]:
			if var[0] == '$':
				self.var_map[var.rstrip()] = self.get_variables(text)
			else:
				raise ParserError("Illegal assignment to a constant '%s'" % var.rstrip())
	
	def get_variables(self, tag, ignore_list=[]):
		# applies variables from the system to current line
		tag = replace_variables(tag, self.var_map, ignore_list)
		return self.resolve_indexes(tag) # this converts notation [item1, item2, item3, ...][1] to item2
	
	def create_method(self, line):
		indent = self.tree.find_indent(line) #this should always be zero
		if line[:4] == 'def ': # this prevents us from overlooking consecutively declared methods
			self.tree.indent = indent
			element, attributes = parse_definition(line[4:])
			
			if element[0] not in string.letters or not element.isalnum():
				raise ParserError("Method name must be alphanumeric and start with a letter")
			
			if element in self.valid_tags.keys():
				raise ParserError("Can't create method named '%s', it's a reserved HTML element name" % element)
			
			self.creating_method = element
			self.method_map[element] = Method(attributes, True, self.color) # methods access shadowed variables to prevent overwriting globals
				
		else:
			if indent == 0:
				self.creating_method = None
				return True #finished
			else:
				self.method_map[self.creating_method].add_line(line[len(self.tree.indent_marker):])
		return False
	
	def unroll_loop(self):
		loop_token = self.loop_stack.pop()
		loop_name = loop_token[0]
		loop_indent = loop_token[1]
		loop_array = loop_token[2]
		self.tree.indent = loop_indent
		for arg in loop_array:
			self.handle_line('%s%s(%s)' % (self.tree.indent_marker*loop_indent, loop_name, arg))
	
	def handle_indent(self, indent, method_name):
		self.tree.handle_indent(self.tree.indent_to(indent) + '|', \
			[self.close_last_element], \
			[self.element_stack.append, method_name])
	
	def create_loop(self, line):
		# we can just piggy-back on create_method, since a loop is essentially a repeated function
		# the only tricky part is that loops can be nested
		tag = line.strip()
		indent = self.tree.find_indent(line)
		if tag[:4] == 'for ':	# new loop started (either within old loop, or outside)
			self.handle_indent(indent, None)
			var = tag.split()[1] #[for,$var,in,...]
			if var in self.var_map.keys():
				raise ParserError("Can't reuse previously defined variable %s as loop iterator" % var)
			
			#array = self.get_variables(tag.split('[')[1].split(']')[0]).split(',')
			#iterator = re.findall('^for[ ]+(\$[a-zA-Z_][a-zA-Z0-9_]*)[ ]+in', tag)[0]
			#array = self.get_variables(tag, [var]).split('[', 1)[1].rsplit(']', 1)[0].split(',')
			array = get_attr('(%s)' % self.get_variables(tag, [var]).split('[', 1)[1].rsplit(']', 1)[0])
			
			for i in range(len(array)):
				array[i] = array[i].strip()
			loop_name = 'loop_def_%s' % self.loop_index
			self.loop_stack.append((loop_name, indent, array))
			self.method_map[loop_name] = Method([var], False, self.color) # loops see/access global var space
			self.loop_index += 1
		else:					# command inside the loop or outside (loop termination)
			loop_name = self.loop_stack[-1][0]
			loop_indent = self.loop_stack[-1][1]
			indent_diff = indent-loop_indent
			if indent_diff < 1:
				# loop terminated, unroll it and execute this line as normal
				self.unroll_loop()
				self.handle_line(line)
			else:
				self.tree.indent = indent
				self.method_map[loop_name].add_line(line[len(self.tree.indent_marker*(loop_indent+1)):])

	def expand_assignment_ops(self, tag, perform=True):
		# takes operation of form '$a += 3', converts it to '$a := $a + 3' and evaluates it, assigning new value to $a
		result, tag = expand_assignment(tag)
		pair = tag.split(':=')
		if len(pair) > 2:
			raise ParserError("Command '%s' has multiple assignment operators, invalid syntax" % tag)
		self.var_map[result] = do_arithmetic(self.get_variables(pair[1].strip()))
		return result
	
	def import_module(self, line):
		tokens = line.split()
		if len(tokens) != 2 or tokens[0] != 'import':
			raise ParserError("Invalid import statement: %s" % line.strip())
		
		if tokens[1] not in self.imported_files:
			try:
				self.imported_files.append(tokens[1])
				self.parse(tokens[1].replace('.', '/') +'.pyml', True)
			except IOError:
				#TODO: make it try to open in parser's directory as well
				raise ParserError("Can't import %s, module doesn't exist" % tokens[1])
	
	def create_template_engine(self, line):
		# creates a new set of rules for a templating engine, such as Django, Web2py, or Rails
		pair = line.split('=')
		if len(pair) != 2:
			raise ParserError("Improper TemplateEngine declaration")
		elif pair[0].isalnum() and pair[0] not in string.letters:
			raise ParserError("TemplateEngine must have alphanumeric name that starts with a letter")
		template = pair[1][pair[1].find('(')+1:pair[1].rfind(')')-1].strip().strip("'").strip('"')
		self.template_engines[pair[0].rstrip()] = TemplateEngine(template)
	
	def parse_template_engine_call(self, line, indent):
		compressed = line.replace(' ','')
		if compressed.find('create(') != -1:
			# add a template to existing template engine
			engine, template, method_call, attr = parse_template_engine_method_declaration(line)
			try:
				if len(attr) == 1:
					self.template_engines[engine].add_method(template, attr[0][1:-1])
				else:
					self.template_engines[engine].add_method(template, attr[0][1:-1], attr[1][1:-1])
			except KeyError:
				raise ParserError("Attempting to add a method to a TemplateEngine prior to declaration")
		elif compressed.find('append(') != -1:
			# append additional logic to a template
			engine, template, method_call, attr = parse_template_engine_method_declaration(line)
			original_pair = method_call.split('.') # we only care about 1st 2 args
			if len(original_pair) != 3:
				raise ParserError("Method being appended to must follow TemplateEngine.MethodName format")
			try:
				self.template_engines[original_pair[0]].enhance_method(original_pair[1], template)
			except KeyError:
				raise ParserError("Attempting to append functionality to a non-existing method")
			try:
				self.template_engines[engine].add_method(template, attr[0][1:-1])
			except KeyError:
				raise ParserError("Attempting to add a method to a TemplateEngine prior to declaration")
		else:
			try:
				# invoke template engine method
				whitespace = self.tree.indent_to(indent)
				method_pair = line.split('(')[0].rstrip().rsplit('.', 1)
				if not self.template_engines[method_pair[0]].is_submethod(method_pair[1], indent):
					end_method = self.template_engines[method_pair[0]].end_method(method_pair[1])
					if end_method is None:
						self.tree.indent = indent
					else:
						self.handle_indent(indent, whitespace + end_method)
				else:
					#note the indent+1, we want to close inner logic, but not the method itself
					endtag = self.template_engines[method_pair[0]].end_method(method_pair[1], False)
					if endtag is None:
						self.handle_indent(indent+1, None)
						self.element_stack.pop()
					else:
						self.handle_indent(indent+1, whitespace + endtag)
				attr = get_attr(line)
				self.write(whitespace + self.template_engines[method_pair[0]].call_method(method_pair[1], attr, indent))
				#self.element_stack.append(whitespace + self.template_engines[method_pair[0]].end_method(method_pair[1]))
			except (KeyError, IndexError, TypeError):
				raise ParserError("Improper TemplateEngine method declaration or invocation")
	
		# helper method for checking if the line involves variable assignment and/or reassignment
		if line.find(':=') != -1:
			# variable declaration
			self.set_variable(line)
			return
		elif line.find('+=') != -1 or line.find('-=') != -1 or line.find('*=') != -1 or line.find('/=') != -1:
			# variable increment
			res = self.expand_assignment_ops(line)
			line = self.var_map[res]
	
	MULTILINE = 0
	SINGLELINE = 1
	def handle_verbatim_declaration(self, tag):
		assignment_pair = tag.split('=', 1)
		newtag = assignment_pair[0].strip()
		element, attributes = parse_definition(assignment_pair[1])
		length = len(attributes)
		if length == 0:
			# no args were passed, this version has no outer tags wrapping the text
			starttag = endtag = ''
		elif length == 1:
			# TODO: eventually we want this to also check declared methods, if available, first
			#if attributes[0] in self.template_engines.keys():
			#	endtag = self.template_engines[attributes[0]].tag_format %
			#else:
			#	endtag = '</%s>\n' % attributes[0]
			
			tagname, tagattr = parse_definition(attributes[0])
			starttag, endtag = create_tag(tagname, tagattr)
		elif length == 2:
			# received 2 quoted arguments for beginning and end tags
			starttag = attributes[0][1:-1] + '\n'
			endtag = attributes[1][1:-1] + '\n'
		else:
			raise ParserError("Verbatim definition takes 0,1, or 2 arguments, %s arguments were given" % length)
		
		# append to verbatim format in (start_tag, end_tag, type) format
		if element == 'verbatim_line':
			self.verbatim[newtag] = (starttag, endtag, self.SINGLELINE)
		else:
			self.verbatim[newtag] = (starttag, endtag, self.MULTILINE)
	
	def handle_verbatim_call(self, line):
		indent = self.tree.find_indent(line)
		if self.current_verbatim is None:
			# this is the first line of verbatim logic
			self.handle_indent(indent, None)
			self.current_verbatim = line.strip().split('(')[0].strip(':')
			self.verbatim_indent = self.tree.find_indent(line)
			if self.verbatim[self.current_verbatim][0] != '':
				self.verbatim_buffer += self.tree.indent_marker*self.verbatim_indent + self.verbatim[self.current_verbatim][0]
			self.last_opened_element = None
			self.element_stack.append(None)
		else:
			# we're continuing to parse existing verbatim logic
			if indent > self.verbatim_indent:
				# still inside verbatim block
				
				# doesn't really serve any purpose, this logic is mostly cosmetic to make indentation pretty
				if self.verbatim[self.current_verbatim][0] == '' and line.find(self.tree.indent_marker) == 0:
					line = line[len(self.tree.indent_marker):]
				
				self.verbatim_buffer += line
			else:
				# end of verbatim logic
				if self.verbatim[self.current_verbatim][1] != '':
					self.verbatim_buffer += self.tree.indent_marker*self.verbatim_indent + self.verbatim[self.current_verbatim][1]
				if self.verbatim[self.current_verbatim][2] == self.SINGLELINE:
					self.verbatim_buffer = re.sub('\n[ 	]*', ' ', self.verbatim_buffer)
					self.verbatim_buffer += '\n'
				self.write(self.verbatim_buffer)
				self.verbatim_buffer = ''
				self.current_verbatim = None
				self.close_last_element() # close verbatim element so it does not screw up the stack
				self.handle_line(line)
	
	def handle_line(self, line):
		indent = self.tree.find_indent(line)
		whitespace = self.tree.indent_to(indent)
		
		#parse the tag
		tag = line.strip()
		
		#if tag[0] == '$' and tag.find(':=') == -1:
		#	tag = self.get_variables(tag)
		
		if self.current_verbatim is not None or tag.split('(')[0].strip(':') in self.verbatim.keys():
			# verbatim call
			# note: even comments inside verbatim block get treated verbatim
			self.handle_verbatim_call(line)
			return
		elif not tag or tag[0] == '#': #line.count('//'):
			# strip comments
			# we can't use Python-style comments because we use # for ID and hex values
			'''
			loc = line.find('//')
			subline = line[:loc]
			#TEMP: this is a naive implementation of quoted string search, we assume all internal quotes
			# are preceded with \ (i.e. 'Bob\'s Gun' = ok, "Bob's Gun" = bug)
			if not (subline.count('"')-subline.count('\"'))%2 and \
			not (subline.count("'")-subline.count("\'"))%2:
				line = subline
				tag = line.strip()
			if not tag:
				return'''
			return
		
		line = expand_arrays(line)
		tag = line.strip()
		
		if tag.find('verbatim') != -1:
			# TODO: replace with regex matching to avoid false positives in cases of method names like this_is_not_verbatim_call()
			# verbatim declaration
			self.handle_verbatim_declaration(tag)
			return
		elif self.loop_stack or tag[:4] == 'for ':
			# loop
			self.create_loop(line)
			return
		elif self.creating_method is not None or line[:4] == 'def ':
			# method definition
			finished = self.create_method(line)
			if not finished:
				return
		elif tag.find(':=') != -1:
			# variable declaration
			self.set_variable(tag)
			return
		elif line.find('+=') != -1 or line.find('-=') != -1 or line.find('*=') != -1 or line.find('/=') != -1:
			# variable increment
			res = self.expand_assignment_ops(line)
			tag = self.var_map[res]
		elif line[:7] == 'import ':
			# import
			self.import_module(line)
			return
		elif line.find('TemplateEngine') != -1:
			# template class declaration
			self.create_template_engine(tag)
			return
		elif tag.find('.') != -1 and tag.split('.')[0].isalnum() and tag.split('.')[0][0] in string.letters:
			# template method declaration or call
			self.parse_template_engine_call(tag, indent)
			return
		
		tag = self.get_variables(tag)
		
		if tag[0] in ('"', "'"):
			# handle quoted strings as plain-text
			starttag = tag[1:-1] + '\n'
			element = None
			htmlend = None
		else:
			# test if this tag is a method call, if so execute it
			element, attributes = parse_definition(tag)
			if element in self.method_map.keys():
				self.handle_indent(indent, None)
				for method_line in self.method_map[element].run_method(attributes, self.var_map):
					if method_line is not None:
						self.handle_line(whitespace+method_line)
				return
			else:
				# this is a regular tag, not a method, let's make sure the element and attributes are valid
				try:
					self.valid_tags[element]
					hash_key = element
				except KeyError:
					try:
						self.valid_tags['*'] # if we can't access this, wildcard element was not declared
						hash_key = '*'
					except KeyError:
						raise ParserError("'%s' is not a valid markup tag or method name." % element)
				
				if self.valid_tags[hash_key][1] is not None:
					for attr in attributes:
						attr_name = attr.split('=', 1)[0]
						if attr_name not in self.valid_tags[hash_key][1]:
							raise ParserError("'%s' is not one of allowed attributes for '%s' element" % (attr_name, hash_key))
		
			starttag, endtag = create_tag(element, attributes)
			htmlend = whitespace + endtag
		
		# check indent difference, close old tags if indent < 1
		self.handle_indent(indent, htmlend)
		
		# update variables
		self.last_opened_element = element
		
		# dump the current line to file
		self.write(whitespace + starttag)
	
	def parse(self, filename, module=False):
		# we assume here that the file is relatively small compared to our allowed buffer
		if not module:
			self.__init__(self.valid_tags) #reset
		line_num = 0
		with open(filename, 'r') as source:
			buffer = ''
			for line in source:
				line_num += 1
				try:
					#parse multi-lines together
					if line[-2:] == '\\\n':
						if buffer:
							line = ' ' + line.lstrip()
						buffer += line[:-2]
						continue
					elif buffer:
						line = buffer + ' ' + line.lstrip()
						buffer = ''
					
					self.handle_line(line)
				except ParserError, (error):
					print "Error in %s: line %d: %s" % (filename, line_num, error.message)
					print repr(line)
					sys.exit()
				except:
					# on all other errors
					print "Error in %s: line %d: %s" % (filename, line_num, "'%s' caused the following uncaught exception:" % line.strip())
					print repr(line)
					raise
		
		# terminate non-finished loops and pop off remaining elements, closing our HTML tags
		while self.loop_stack:
			self.unroll_loop()
		while self.element_stack:
			self.close_last_element()
		return self.output
