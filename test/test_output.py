# -*- coding: UTF-8 -*-
from __future__ import division

import os
test_dir = os.path.dirname(__file__)
tmp_dir = os.path.join(test_dir, '.tmp')

import tempfile


bin_path = os.path.join(test_dir, os.path.pardir, 'bin', 'pydflatex')

## mod_path = os.path.join(test_dir, os.path.pardir)
## import sys
## sys.path.insert(0, mod_path)
## print sys.path

from subprocess import Popen, PIPE

import re

import nose.tools as nt

try:
	import pygments
except ImportError:
	success = ''
	failure = ''
	ref_warning = ''
	warning = ''
else:
	success = '\x1B[32;01m'
	failure = '\x1B[31;01m'
	ref_warning = "\x1B[35;01m"
	warning = '\x1B[35;01m'

class Test_Output(object):
	
	def setUp(self):
		from pydflatex import Typesetter
		from pydflatex.typesetter import LaTeXLogger
		self.t = Typesetter()
		self.t.clean_up_tmp_dir()
		self.logfile = tempfile.NamedTemporaryFile()
		import logging
		self.handler = logging.FileHandler(self.logfile.name)
		logger = LaTeXLogger('log')
		logger.addHandler(self.handler)
		self.t.logger = logger
		
	def tearDown(self):
		self.t.logger.removeHandler(self.handler)
		self.logfile.close()
	
## 	def mk_tmp(self, content):
## 		import tempfile
## 		f = tempfile.NamedTemporaryFile(suffix='.tex', dir=tmp_dir)
## 		f.write(content)
## 		return f
## 	
	def typeset(self, file_name, with_binary=False):
		if with_binary:
			self.output = Popen([bin_path, file_name], stderr=PIPE).communicate()[1]
		try:
			self.t.run(os.path.join(test_dir, file_name))
		except Exception, e:
			return e
		finally:
			self.output = self.logfile.read()

	def assert_contains(self, match, line=None, regexp=False):
		out = self.output
		if line is not None:
			out = out.splitlines()[line]
		if not regexp:
			does_match = out.find(match) != -1
		else:
			does_match = re.search(match, self.output)
		if not does_match:
			raise AssertionError("'%s' not in\n%s" % (match, out))
	
	def assert_success(self):
		self.assert_contains('Typesetting of')
		self.assert_contains('completed')
		self.assert_contains(success)
			
	def test_simple(self):
		self.typeset('simple')
		self.assert_contains('Typesetting %s/simple.tex' % test_dir, 0)
		self.assert_contains('Typeset', -1)
		self.assert_contains(success)
	
	def test_error(self):
		e = self.typeset('error')
		nt.assert_true(isinstance(e,IOError))
		self.assert_contains(r'3: Undefined control sequence \nonexistingmacro.')
		self.assert_contains(failure)
	
	def test_non_exist(self):
		self.typeset('nonexistent')
		self.assert_contains(failure)
		self.assert_contains('File %s/nonexistent.tex not found' % test_dir)
	
	def test_wrong_ext(self):
		self.typeset('simple.xxx')
		self.assert_contains('Wrong extension for %s/simple.xxx' % test_dir)
		self.assert_contains(failure)
	
	def test_trailing_dot(self):
		self.typeset('simple.')
		self.assert_success()
	
	def test_ref(self):
		self.typeset('ref')
		self.assert_contains("undefined")
		self.assert_contains("nonexistent")
		self.assert_contains('There were undefined references.', -2)
## 		self.assert_contains(ref_warning, -4)
		self.assert_contains(warning, -2)
	
	def test_rerun(self):
		self.typeset('rerun')
		self.assert_contains('Rerun')
		self.assert_contains('pdflatex run number 2')
		self.assert_success
	
	def test_twice_label(self):
		self.typeset('twicelabel')
		self.assert_contains(warning,-2)
		self.assert_contains(warning,-3)
		self.assert_contains("Label `label' multiply defined", -3)
		self.assert_contains("There were multiply-defined labels", -2)
	
	def test_cite(self):
		self.typeset('cite')
		self.assert_contains('citation')
		self.assert_contains(failure)
## 	def test_no_tmp_dif(self):
## 		self.t.typeset_file('simple')
	
	def test_binary(self):
		self.typeset('simple', with_binary=True)
		self.assert_contains('Typesetting %s/simple.tex' % test_dir, 0)
	