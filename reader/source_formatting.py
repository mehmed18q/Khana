"""Whitespace formatting for structured documents without sorting their data."""

import json
import re
from io import StringIO
from xml.dom import Node, minidom
from xml.parsers import expat

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import DocumentStartEvent, ScalarEvent

from reader.documents import MAX_FILE_BYTES

FORMATTABLE = frozenset({"JSON", "YAML", "XML"})


class _LimitedOutput(StringIO):
    def write(self, text):
        if self.tell() + len(text) > MAX_FILE_BYTES:
            raise ValueError("The formatted result would exceed the 5 MB document limit.")
        return super().write(text)


def _json(source):
    def invalid_constant(value):
        raise ValueError(f"{value} is not a valid JSON value.")

    # Validate without converting numbers to floats. Then reindent the tokens
    # themselves, retaining exact numbers, escape sequences, and duplicate keys.
    json.loads(source, parse_int=str, parse_float=str, parse_constant=invalid_constant)
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|[^\s{}\[\],:]+|[{}\[\],:]', source)
    output = _LimitedOutput()
    depth = 0
    for index, token in enumerate(tokens):
        if token in ("{", "["):
            output.write(token)
            depth += 1
            if tokens[index + 1] not in ("}", "]"):
                output.write("\n" + "  " * depth)
        elif token in ("}", "]"):
            depth -= 1
            if tokens[index - 1] not in ("{", "["):
                output.write("\n" + "  " * depth)
            output.write(token)
        elif token == ",":
            output.write(",\n" + "  " * depth)
        elif token == ":":
            output.write(": ")
        else:
            output.write(token)
    return output.getvalue() + "\n"


def _yaml(source):
    yaml = YAML(typ="rt", pure=True)
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 100
    # Parse/emit events without constructing Python values: timestamps, large
    # numbers, tags, anchors, aliases and per-document YAML versions stay intact.
    events = list(yaml.parse(source))
    if not any(isinstance(event, DocumentStartEvent) for event in events):
        return source  # A blank or comment-only YAML file has no document event.
    for event in events:
        if isinstance(event, ScalarEvent):
            # The round-trip emitter also expects the standard-tag flag that
            # its serializer supplies; parser events only contain two flags.
            event.implicit = (
                *event.implicit,
                bool(event.tag and event.tag.startswith("tag:yaml.org,2002:")),
            )
    output = _LimitedOutput()
    yaml.emit(events, output)
    return output.getvalue()


def _xml(source):
    def reject_dtd(*_):
        raise ValueError("XML with a DTD cannot be formatted. The source was kept unchanged.")

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = reject_dtd
    parser.Parse(source, True)

    def pretty(node, depth=0, preserve=False):
        prefix = "  " * depth
        if node.nodeType != Node.ELEMENT_NODE:
            return prefix + node.toxml()
        space = node.getAttribute("xml:space")
        preserve = True if space == "preserve" else False if space == "default" else preserve
        # In mixed content, adding whitespace changes the text being read.
        if preserve or any(
            child.nodeType == Node.CDATA_SECTION_NODE
            or (
                child.nodeType == Node.TEXT_NODE
                and (
                    child.data.strip(" \t\r\n")
                    or (child.data and "\n" not in child.data and "\r" not in child.data)
                )
            )
            for child in node.childNodes
        ):
            return prefix + node.toxml()
        children = [
            child
            for child in node.childNodes
            if child.nodeType != Node.TEXT_NODE or child.data.strip(" \t\r\n")
        ]
        if not children:
            return prefix + node.toxml()
        opening = node.cloneNode(False).toxml()[:-2] + ">"
        return (
            prefix
            + opening
            + "\n"
            + "\n".join(pretty(child, depth + 1, preserve) for child in children)
            + "\n"
            + prefix
            + f"</{node.tagName}>"
        )

    with minidom.parseString(source) as document:
        declaration = re.match(r"<\?xml\s.*?\?>", source, re.DOTALL)
        lines = [declaration.group(0)] if declaration else []
        lines.extend(
            pretty(node) for node in document.childNodes if node.nodeType != Node.TEXT_NODE
        )
        return "\n".join(lines) + "\n"


def beautify_source(source, document_format):
    if document_format not in FORMATTABLE:
        raise ValueError("Format document is available for JSON, YAML and XML.")
    if len(source.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("This document is too large to format (limit: 5 MB).")
    try:
        result = {"JSON": _json, "YAML": _yaml, "XML": _xml}[document_format](source)
    except YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise ValueError(
            f"Invalid YAML{location}: {getattr(error, 'problem', None) or str(error)[:200]}"
        ) from error
    except expat.ExpatError as error:
        raise ValueError(f"Invalid XML: {error}") from error
    except RecursionError as error:
        raise ValueError("This document is nested too deeply to format.") from error
    if len(result.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("The formatted result would exceed the 5 MB document limit.")
    return result
