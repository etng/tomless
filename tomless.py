#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import re
import json
import datetime
import logging
from collections import namedtuple
from dateutil.parser import parse as parse_datetime

__version__ = '0.1.0'
__author__ = 'etng <etng2004@gmail.com>'
__all__ = (
    'TomlTokenizer',
    'TomlParser',
)

TomlToken = namedtuple('TomlToken', 'type, val, row_no, col_no')

def unescape(s):
    escaping_map = (
        (r'\t', "\t", ),
        (r'\n', "\n", ),
        (r'\r', "\r", ),
    )
    for src, dst in escaping_map:
        s = s.replace(src, dst)
    try:
        s = s.decode('utf-8')
    except Exception as e:
        print(e.message)
    return s

class TomlTokenizer(object):
    PATTERNS = (
        ('bool', re.compile('(true|false)'), lambda x: x == 'true'),
        ('comment', re.compile(r'(#[\s\S]*)'), lambda x: x[1:].strip()),
        ('id', re.compile(r'([_a-zA-Z][a-zA-Z0-9_]*)'), None),
        ('section', re.compile(r'(\[[_a-zA-Z][a-zA-Z0-9_]*(\.[_a-zA-Z][a-zA-Z0-9_]*)*\])'), lambda x: x[1:-1].strip()),
        ('string', re.compile('("[^"]*")'), lambda x: unescape(x[1:-1].strip())),
        ('whitespace', re.compile('(\s+)'), lambda x: None),
        ('literal', re.compile(r'([,\[\]=])'), None),
        ('datetime', re.compile('(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([-+]\d{2}:?\d{2}|Z))'), lambda x: parse_datetime(x)),
        ('float', re.compile('(\d+\.\d+)'), lambda x: float(x)),
        ('int', re.compile('(\d+)'), lambda x: int(x)),
    )
    LOGGER_NAME = 'tomless.tokenizer'

    @classmethod
    def tokenize_line(cls, line, line_no):
        offset = 0
        logger = logging.getLogger(cls.LOGGER_NAME)
        logger.debug('tokenlizing line {} {}'.format(line_no, line))
        line = line.strip()
        while offset < len(line):
            current_offset = offset
            for t_type, pattern, processor in cls.PATTERNS:
                logger.debug('try pattern {} at offset {}'.format(t_type, offset))
                match = pattern.match(line, offset)
                if not match:
                    logger.debug('no match')
                    continue
                content = match.group(0)
                content_length = len(content)
                val = processor(content) if processor else content
                if t_type != 'whitespace':
                    yield TomlToken(val if t_type == 'literal' else t_type, val, line_no, offset)
                offset += content_length
                logger.debug('matched pattern {} {} ({})'.format(t_type, content, content_length))
            if current_offset == offset:
                raise Exception('lex error at line {} {}: {}'.format(line_no, current_offset, line))
            logger.debug('check eol:{} {} {}'.format(offset, len(line), line[offset:]))

    @classmethod
    def tokenize_content(cls, content):
        for i, line in enumerate(content.strip().splitlines()):
            for token in cls.tokenize_line(line, i+1):
                yield token

    @classmethod
    def tokenize_file(cls, filename):
        content = ''
        with open(filename) as f:
            content = f.read()
        return list(cls.tokenize_content(content))

class TomlParser(object):
    LOGGER_NAME = 'tomless.parser'

    @classmethod
    def parse_content(cls, content):
        return cls(list(TomlTokenizer.tokenize_content(content))).parse()

    @classmethod
    def parse_file(cls, filename):
        content = ''
        with open(filename) as f:
            content = f.read()
        return cls(list(TomlTokenizer.tokenize_content(content))).parse()

    def __init__(self, tokens):
        self.tokens = tokens
        self.result = {}
        self.context = {}
        self.status_history = []
        self.section_history = []
        self.token_history = []
        self.value_stack = []
        self.logger = logging.getLogger(self.__class__.LOGGER_NAME)

    def __getattr__(self, attr):
        '''
        fetch method from current status related class and bind self to it,
        so all the static method of status class will be treated as the
        Parser Class's member method
        '''
        klass = getattr(self, self._status)
        meth = getattr(klass, attr, None)
        if callable(meth):
            def _(*args, **kwargs):
                return meth(self, *args, **kwargs)
            return _
        return meth

    def parse(self):
        self.logger.debug('parse begin')
        self.enter('StatusBuildSection', '')
        for token in self.tokens:
            if token.type in ('comment', ):
                continue
            self.feed(token)
        self.feed(TomlToken('eof', '', None, None))
        self.exit()
        self.logger.debug('parse end, taking snapshot')
        self.logger.debug('section_history %s', self.section_history)
        self.logger.debug('status_history %s', self.status_history)
        self.logger.debug('value_stack %s', self.value_stack)
        self.logger.debug('parse end, taked snapshot')
        return self.result

    def exit(self):
        current_status = self.status_history.pop()
        self.logger.debug('exiting status %s, %s', current_status, current_status == self._status)
        self._on_exit()
        if self.status_history:
            last_status = self.status_history.pop()
            self.logger.debug('reenter status %s', last_status)
            self.enter(last_status)

    def enter(self, status, *args, **kwargs):
        self._status = status
        self.status_history.append(status)
        self.logger.debug('before _on_enter %s %s %s', status, args, kwargs)
        self._on_enter(*args, **kwargs)

    def combine_values(self, stop_type=None):
        if stop_type:
            self.logger.debug('combine values until meet type {}'.format(stop_type))
            vals = []
            while True:
                val = self.value_stack.pop()
                self.logger.debug('found val {} {}'.format(val.type, val.val))
                if val.type == stop_type:
                    self.logger.debug('stopped now {}'.format(val))
                    break
                vals.append(val.val)
            return TomlToken('list', list(reversed(vals)), None, None)
        else:
            val = self.value_stack.pop()
            return val


    class StatusBase(object):

        @staticmethod
        def _on_enter(self, *args, **kwargs):
            pass

        @staticmethod
        def _on_exit(self, *args, **kwargs):
            pass

    class StatusBuildSection(StatusBase):

        @staticmethod
        def sync_result(self, section_name):
            self.logger.debug('before sync_result %s %s', section_name, self.context)
            if not self.context:
                self.logger.debug('no context, ignore sync_result')
                return
            if section_name:
                parent = self.result
                parts = section_name.split('.')
                for part in parts:
                    parent.setdefault(part, {})
                    parent = parent[part]
                parent.update(self.context)
            else:
                self.result.update(self.context)
            self.context = {}
            self.logger.debug('after sync_result %s %s %s', section_name, self.result, self.context)

        @staticmethod
        def _on_enter(self, name=None, *args, **kwargs):
            self.sync_result(self._section_name)
            if name is None and self.section_history:
                name = self.section_history.pop()
            self.section_history.append(name)
            self._section_name = name
            self.logger.debug('current result %s', self.result)
            self.logger.debug('in section {}'.format(name if name else 'ROOT'))

        @staticmethod
        def feed(self, token):
            if token.type in ('id', ):
                self.var = token.val
            elif token.type in ('=', ):
                self.enter('StatusBuildValue')
            elif token.type in ('section', ):
                self.enter('StatusBuildSection', token.val)
            else:
                self.logger.error('unknown token %s %s', token.type, token.val)

        @staticmethod
        def _on_exit(self):
            self.sync_result(self._section_name)


    class StatusBuildValue(StatusBase):

        @staticmethod
        def _on_enter(self, *args, **kwargs):
            self.logger.debug('build value for %s', self.var)
            pass

        @staticmethod
        def feed(self, token):
            if token.type in ('id', ']', 'section', 'eof', ):
                self.exit()
                if token.type in ('id', 'section', ):
                    self.feed(token)
                # if token.type == 'id':
                #     self.var = token.val
                # elif token.type == 'section':
                #     self.enter('StatusBuildSection', token.val)
            elif token.type in ('int', 'float', 'string', 'datetime', 'bool', ):
                self.logger.debug('push value stack: %s', token)
                self.value_stack.append(token)
            elif token.type in ('[', ):
                self.enter('StatusBuildList', token)
            else:
                self.logger.error('unknown value: %s %s', token.type, token.val)

        @staticmethod
        def _on_exit(self):
            if self.value_stack:
                val = self.combine_values()
                self.logger.debug('assign: %s = %s', self.var, val.val)
                self.context[self.var] = val.val
            else:
                self.logger.error('empty value stack for var %s', self.var)


    class StatusBuildList(StatusBase):

        @staticmethod
        def _on_enter(self, token=None, *args, **kwargs):
            self.logger.debug('building list')
            if token is None:
                if self.token_history:
                    token = self.token_history.pop()
            else:
                self.token_history.append(token)
                self.value_stack.append(token)

        @staticmethod
        def feed(self, token):
            if token.type in (',', ):
                self.logger.debug('pass list ,')
                pass
            elif token.type in ('[', ):
                self.logger.debug('list in list')
                self.logger.debug('enter list now %s', token)
                self.enter('StatusBuildList', token)
            elif token.type in (']', ):
                self.logger.debug('exit list on ]')
                self.exit()
            elif token.type in ('int', 'float', 'string', 'datetime', 'bool', ):
                self.logger.debug('got list value %s', token.val)
                self.value_stack.append(token)
            else:
                self.logger.debug('list unknown: %s %s', token.type, token.val)

        @staticmethod
        def _on_exit(self):
            val = self.combine_values('[')
            self.value_stack.append(val)
            self.logger.debug('found list %s', val)

class MyJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            return json.JSONEncoder.default(self, obj)

from xml.etree import ElementTree as Tree

class XmlEncoder(object):
    '''
    >>> d = dict(a=1, b=u'hello world', c=[1,2,3,4])
    >>> print XmlEncoder(root_tag='toml', item_tag='item').encode(d)
    <toml><item><a>1</a><c><item>1</item><item>2</item><item>3</item><item>4</item></c><b>hello world</b></item></toml>
    '''
    def __init__(self, root_tag='root', item_tag='item'):
        self.root_tag = root_tag
        self.item_tag = item_tag

    def encode(self, v):
        root = Tree.Element(self.root_tag)
        self.encode_node(root, v)
        return Tree.tostring(root)

    def encode_node(self, parent, v, k=None):
        child = Tree.SubElement(parent, self.item_tag if k is None else k)
        if isinstance(v, dict):
            for k, _v in v.items():
                self.encode_node(child, _v, k)
        elif isinstance(v, (tuple, list)):
            for _v in v:
                self.encode_node(child, _v)
        else:
            child.text = unicode(v)


def selftest():
    files = (
        # 'basic.toml',
        # 'nest_list.toml',
        # 'sections.toml',
        'example.toml',
    )
    # print(list(TomlTokenizer.tokenize_content(content)))
    # print(TomlParser.parse_content(content))
    from pprint import pprint
    import os
    for filename in files:
        filename = os.path.join('data', filename)
        print('test file ', filename)
        # print(list(TomlTokenizer.tokenize_file(filename)))
        result = TomlParser.parse_file(filename)
        pprint(result)
        print(json.dumps(result, sort_keys=True, indent=2, cls=MyJsonEncoder))

def print_or_save(filename, content):
    if not filename:
        print(content)
        return
    with open(filename, 'wb') as f:
        f.write(content)

def execute():
    all_log_level = logging.DEBUG
    token_log_level = logging.INFO
    parse_log_level = logging.INFO
    log_filename = None

    import argparse
    parser = argparse.ArgumentParser(description='TOML file parser')
    parser.add_argument("-f", "--format", default="json", help="导出的数据格式，可选值为 json/xml/dict/ppdict ，默认是 json")
    parser.add_argument("-o", "--output", default=None, help="输出结果文件位置，不提供则直接显示, 当数据格式为 json/xml 时有效")
    parser.add_argument("-l", "--log_filename", default=None, help="日志文件保存位置，不提供则直接显示")
    parser.add_argument("-v", "--verbose", default='info', help="日志详细级别，可选的有 info,debug,error 等，默认为info")
    parser.add_argument('filename', nargs=1, help="需要解析的 toml 文件名称")
    args = parser.parse_args()

    new_log_level = getattr(logging, args.verbose.upper(), logging.INFO)
    all_log_level = token_log_level = parse_log_level = new_log_level
    if args.log_filename:
        log_filename = args.log_filename
    logging.basicConfig(
        filename=log_filename,
        level=all_log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    logging.getLogger('tomless.tokenizer').setLevel(token_log_level)
    logging.getLogger('tomless.parser').setLevel(parse_log_level)

    filename = args.filename[0]
    result = TomlParser.parse_file(filename)
    if args.format == 'json':
        print_or_save(args.output, json.dumps(result, sort_keys=True, indent=2, cls=MyJsonEncoder))
    if args.format == 'xml':
        print_or_save(args.output, XmlEncoder(root_tag='toml', item_tag='item').encode(result))
    elif args.format == 'ppdict':
        from pprint import pprint
        pprint(result)
    else:
        print(result)

if __name__ == '__main__':
    execute()
