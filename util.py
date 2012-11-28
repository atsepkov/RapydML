class ParserError(Exception):
	"""
	Helper class for standardizing error messages
	"""
	
	def __init__(self, message):
		self.message = message
	
	def __str__(self):
		return self.message

class ShellError(ParserError):
	"""
	Helper class for OS-generated error messages when using code_block
	"""
	pass

class IndentParser:
	def __init__(self):
		self.indent = 0
		self.indent_marker = None
		self.no_stack = True
	
	def find_indent(self, line):
		# return the indentation level for current line
		if line[0] not in ('\t', ' '):
			return 0
		indent = line[:len(line)-len(line.lstrip())]
		
		# if this is the first time we see an indent, make this our template
		if self.indent_marker is None:
			self.indent_marker = indent
			return 1
		return len(indent)/len(self.indent_marker) # we assume uniform whitespace here
	
	def handle_indent(self, line, dedent_callback, indent_callback):
		# dedent_callback and indent_callback are in [funcptr, arg1, arg2, ...] format
		indent = self.find_indent(line)
		indent_diff = indent - self.indent
		# push to or pop from the stack, depending on indent
		if indent_diff < 1 and not self.no_stack: #pop
			while indent_diff < 1:
				dedent_callback[0](*dedent_callback[1:])
				indent_diff += 1
		elif indent_diff > 1:
			raise ParserError('Incorrect indentation')
		indent_callback[0](*indent_callback[1:])
		self.no_stack = False
		self.indent = indent
	
	def indent_to(self, num):
		# return indentation of requested size
		if num == 0:
			return ''
		else:
			return self.indent_marker * num
