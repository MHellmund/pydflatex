#!/usr/bin/env python
# (c) Olivier Verdier <olivier.verdier@gmail.com>, 2007-2010
"""
A wrapper around pdflatex to allow:
- hiding of the temporary files in various ways
- running pdflatex blazingly fast using the -batchmode option
	and returning feedback by parsing the log file.
"""

import os
import shutil


import logging
try:
	from termcolor import colored
except ImportError:
	import warnings
	warnings.warn('termcolor was not found: in black and white it will be')
	def colored(msg, *args, **kwargs):
		return msg

class LaTeXLogger(logging.Logger):
	line_template = 'L{0:5}'
	page_template = 'p.{0:4}'
	package_template = '[{0}]'
	head_template = '{package}{page}{line}: '
	
	colours = {
	 	'success': {'color': 'green', 'attrs':['bold']},
		'error' : {'color': 'red', 'attrs': ['bold']},
		'ref_warning' : {'color': 'red', 'attrs':['bold']},
		'warning' : {'color': 'magenta'},
		'box' : {'color': 'cyan'},
		'info': {'attrs': ['bold']}
		}
	
	def box_warning(self, info):
		"""
		Box (over/underfull) warnings.
		"""
		head = self.get_page_line(info)
		msg = info['text']
		self.info('{head}{message}'.format(head=head, message=colored(msg, **self.colours['box'])))
	
	def warning(self, msg):
		"""
		LaTeX warning
		"""
		logging.Logger.warning(self, msg)
	
	def get_page_line(self, info):
		"""
		Extract the page and line information and formats it.
		"""
		line = info.get('line','')
		page = info.get('page','')
		line_str = self.line_template.format(line)
		page_str = self.page_template.format(str(page).strip())
		package = info.get('pkg','')
		package_str = self.package_template.format(package) and package
		if line_str or page_str:
			return self.head_template.format(package=package_str, page=page_str, line=line_str)
		return ''
			
	
	def latex_warning(self, warning):
		"""
		Extract the info from the `warning` object.
		"""
		msg = warning['text']
		if msg.find('There were') == 0: # for ['There were undefined references.', 'There were multiply-defined labels.']
			return self.error(msg)
		if msg.find('Rerun to get cross-references right.'):
			return self.warning(colored(msg,**self.colours['warning']))
		head = self.get_page_line(warning)
		msg = '{head}{warning}'.format(head=head, warning=colored(msg, **self.colours['warning']))
		self.warning(msg)
	
	def latex_error(self, error):
		logging.Logger.error(self, "{file}:{line}: {error}".format(file=error['file'], line=error.get('line',''), error=colored(error['text'], **self.colours['error'])))
		if error.get('code'): # if the code is available we print it:
			self.message("{line}:\t {code}".format(line=self.line_template.format(error.get('line','')), code=error['code']))

	def error(self, msg):
		"""
		Error (coloured)
		"""
		logging.Logger.error(self, colored(msg, **self.colours['error']))
	
	def success(self, msg):
		"""
		Success (coloured)
		"""
		self.info(colored(msg, **self.colours['success']))
	
	def ref_warning(self, ref):
		"""
		Special format for citation and reference warnings.
		"""
		head = self.get_page_line(ref)
		undefined = ref.get('ref','')
		citation = ref.get('cite', '')
		if undefined:
			self.info("{head}'{reference}' {undefined}".format(head=head, reference=colored(undefined, **self.colours['ref_warning']), undefined='undefined'))
		elif citation:
			self.info("{head}[{citation}] {undefined}".format(head=head, citation=colored(citation, **self.colours['ref_warning']), undefined='undefined'))
		else:
			self.latex_warning(ref)
	
	def message(self, msg):
		"""
		Messages in bold
		"""
		self.info(colored(msg, **self.colours['info']))
	


latex_logger = LaTeXLogger('pydflatex')
latex_logger.setLevel(logging.DEBUG)

std_handler = logging.StreamHandler()
std_handler.setLevel(logging.INFO)

debug_handler = logging.StreamHandler()
debug_handler.setLevel(logging.DEBUG)

## formatter = logging.Formatter('%(message)s')
## handler.setFormatter(formatter)

class LaTeXError(Exception):
	"""
	LaTeX Error
	"""

class Typesetter(object):
	def __init__(self, **options):
		# storing the options
		for k, v in options.items():
			self.__setattr__(k,v)
		# loading the log parser
		from pydflatex.latexlogparser import LogCheck
		self.parser = LogCheck()
		self.tmp_dir = self.create_tmp_dir()
		self.logger = latex_logger
		if not self.debug:
			self.logger.addHandler(std_handler)
		else:
			self.logger.addHandler(debug_handler)
		self.logger.debug(options)

	# maximum number of pdflatex runs
	max_run = 5
	
	tmp_dir_name = '.latex_tmp'
	
	halt_on_errors = True
	
	open_pdf = False
	
	clean_up = False
	
	extra_run = False
	
	debug = False
	
	# whereas the pdf file produced will be pulled back in the current directory
	move_pdf_to_curdir = True
	
	new_pdf_name = ''
	
	suppress_box_warning = False

	# extensions of the files that will be "pulled back" to the directory where the file is
	# on Mac OS X those files will be set invisible
	move_exts = ['pdfsync','pdf']

	
	def create_tmp_dir(self, base=os.path.curdir):
		"""
		Create the temporary directory if it doesn't exist
		return the tmp_dir
		"""
		tmp_dir = os.path.join(base, self.tmp_dir_name)
		if not os.path.isdir(tmp_dir):
			try:
				os.mkdir(tmp_dir)
			except OSError:
				raise IOError('A file named "{0}" already exists in this catalog'.format(tmp_dir))
		return tmp_dir
	
	def rm_tmp_dir(self):
		"""
		Remove the temporary dir. Useful for testing purposes.
		"""
		shutil.rmtree(self.tmp_dir)
	
	def clean_up_tmp_dir(self):
		"""
		Cleans up the tmp dir, i.e., deletes it and create a new pristine one.
		"""
		self.rm_tmp_dir()
		self.create_tmp_dir()

	
	def run(self, file_paths):
		"""
		Compile several files at once
		"""
		# clean up first if needed
		if self.clean_up:
			self.clean_up_tmp_dir()
		# easier to write with one file
		if not isinstance(file_paths, (list, tuple)):
			file_paths = [file_paths]
		for tex_path in file_paths:
			self.typeset_file(tex_path)
	
	def parse_log(self, log_file):
		"""
		Read the log file and print out the gist of it.
		"""
		parser = self.parser
		parser.read(log_file)
		for box in parser.get_boxes():
			has_occ = box['text'].find(r' has occurred while \output is active')
			if has_occ != -1:
				box['text'] = box['text'][:has_occ]
			if not self.suppress_box_warning:
				self.logger.box_warning(box)
		for ref in parser.get_references():
			self.logger.ref_warning(ref)
		for warning in parser.get_warnings():
			# following should be filtered via the loggers filter!
			if warning.get('pkg') == 'hyperref' and warning['text'].find('Token') != -1:
				continue # I hate those hyperref warning
			self.logger.latex_warning(warning)
		errors = list(parser.get_errors())
		if errors:
			for error in errors:
				self.logger.latex_error(error)
			return errors[0]
	
	def move_auxiliary(self, base, file_base):
		"""
		Move some auxiliary files back to the tex directory
		"""
		for aux_ext in self.move_exts:
			aux_name = file_base + os.path.extsep + aux_ext
			src = os.path.join(self.tmp_dir, aux_name)
			dest = os.path.join(base,os.curdir)
			# move the pdf in the current directory
			if aux_ext == 'pdf':
				pdf_name = os.path.join(base, aux_name)
				pdf_path = pdf_name
				if self.move_pdf_to_curdir:
					pdf_path = os.path.join(os.curdir, aux_name)
					pdf_name = aux_name
				if self.new_pdf_name:
					pdf_path = os.path.join(dest,self.new_pdf_name + os.path.extsep + 'pdf')
					pdf_name = dest
				# store the pdf name for later use
				self.current_pdf_name = pdf_name
				# write the pdf data in the existing pdf file
				old_pdf_file = open(pdf_path, 'w')
				try:
					new_pdf_file = open(src, 'r')
				except IOError:
					message = 'pdf file "{0}" not found.'.format(aux_name)
## 					self.logger.error('\n\t%s' % message)
					raise IOError(message)
				contents = new_pdf_file.read()
				old_pdf_file.write(contents)
				old_pdf_file.close()
				new_pdf_file.close()
			else:
				final_path = os.path.join(dest, aux_name)
				try:
					shutil.move(src, final_path)
				except IOError:
					pass
				else:
					if os.uname()[0] == 'Darwin': # on Mac OS X we hide all moved files...
						if os.system('/Developer/Tools/SetFile -a V {0}'.format(final_path)):
							self.logger.info("Install the Developer Tools if you want the auxiliary files to get invisible")



	def typeset_file(self, tex_path, extra_run=None):
		"""
		Typeset one given file.
		"""
		import time
		if extra_run is None:
			extra_run = self.extra_run
		time_start = time.time()
		# find out the directory where the file is
		base,file_name = os.path.split(tex_path)
		file_base, file_ext = os.path.splitext(file_name)
		# setup the TEXINPUTS variable
		os.environ['TEXINPUTS'] = base + ':'
		# find out the name of the file to compile
		root, file_ext = os.path.splitext(tex_path)
		if file_ext[1:]:
			if file_ext[1:] != 'tex':
				self.logger.error("Wrong extension for {0}".format(tex_path))
				return
			else:
				full_path = tex_path
		else:
			full_path = root + os.path.extsep + 'tex'
		
		# make sure that the file exists
		if not os.path.exists(full_path):
			self.logger.error('File {0} not found'.format(full_path))
			return


		# log file
		log_file = os.path.join(self.tmp_dir, file_base + os.path.extsep + 'log')

		self.logger.info('Typesetting {0}\n'.format(full_path))
		
		# preparing the extra run slot
		self.extra_run_slot = extra_run
		
		for run_nb in range(self.max_run):
			# run pdflatex
			self.logger.message("pdflatex run number {0}".format(run_nb + 1))
			arguments = ['pdflatex', '-etex',
				'-no-mktex=pk',
				'-interaction=batchmode',
				'-output-directory={0}'.format(self.tmp_dir), root
				]
			if self.halt_on_errors:
				arguments.insert(-1, '-halt-on-error')
			self.logger.debug(arguments)
			import subprocess
			output = subprocess.Popen(arguments, stdout=subprocess.PIPE).communicate()[0]
			self.logger.message(output.splitlines()[0])
			try:
				error = self.parse_log(log_file)
			except KeyboardInterrupt:
				self.logger.error("Keyboard Interruption")
				import sys
				sys.exit()
			except IOError: # if the file is invalid or doesn't exist
				self.logger.error("Log file not found")
				raise
			except ValueError:
				self.logger.error("Wrong format of the log file")
				raise # stop processing this file
			else:
				if error and self.halt_on_errors:
					raise LaTeXError(error.get('text'))
				self.move_auxiliary(base,file_base)
			# we stop if no other run is needed
			if not self.parser.run_needed():
				if self.extra_run_slot > 0: # run some more times
					self.extra_run_slot -= 1
				else:
					break

		time_end = time.time()
		self.logger.success('Typesetting of "{name}" completed in {time:.1f}s.'.format(name=full_path, time=(time_end - time_start)))
		if self.open_pdf:
			self.logger.info('Opening "{0}"...'.format(self.current_pdf_name))
			os.system('/usr/bin/open "{0}"'.format(self.current_pdf_name))
