![Python Versions](https://img.shields.io/badge/python-2.7-blue.svg)

# tomless

A toml language file parser made for less dependency

## install

```
pip install -e git+git@github.com:etng/tomless.git@master#egg=tomless
```

## usage

### cli

```
tomless example.toml -o example.json
tomless example.toml -f json -o example.json
tomless example.toml -f dict -o example.txt
tomless example.toml -f dict

tomless example.toml -f json|pretty json
```

### code

```
from tomless import TomlParser
result = TomlParser.parse_file('example.toml')
print toml
```


## known issues

* can not parse escaped quote char in string due to regexp limit
* should merge regexp to improve tokenlize speed
* many others

## thanks

* [PLY (Python Lex-Yacc)](http://www.dabeaz.com/ply/)