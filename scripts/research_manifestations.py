#!/usr/bin/env python3
"""Reproduce declared evidence coordinates from an independently obtained source.

No retrieval, publication or source approval occurs. Raw bodies remain outside
the public package; a digest mismatch stops extraction instead of moving a locator.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess

KINDS = ('raw_utf8_lf', 'html_textnodes_v1', 'pdf_physical_page_layout')


class TextNodes(HTMLParser):
    """Exact v1 recipe; text nodes need not be visible in a rendered browser."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored = []
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.ignored.append(tag)

    def handle_endtag(self, tag):
        if tag in self.ignored:
            self.ignored = self.ignored[:len(self.ignored) - 1 - self.ignored[::-1].index(tag)]

    def handle_data(self, value):
        if not self.ignored and value.strip():
            self.nodes.append(value.strip())


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def _check_digest(body, expected, label):
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError(label + ' requires a lowercase SHA-256 digest')
    if sha256(body) != expected:
        raise ValueError(label + ' digest mismatch; do not reuse these coordinates')


def extract(body, kind, *, source_sha256, physical_page=None, pdf_path=None,
            tool_version=None, expected_sha256=None):
    """Return exact UTF-8 manifestation bytes; never normalize line boundaries."""
    _check_digest(body, source_sha256, 'Source response')
    if kind not in KINDS:
        raise ValueError('Unknown manifestation recipe')
    if kind != 'pdf_physical_page_layout':
        if physical_page is not None:
            raise ValueError('Physical page applies only to PDF layout extraction')
        text = body.decode('utf-8', errors='strict')
        if kind == 'raw_utf8_lf':
            result = body
        else:
            parser = TextNodes()
            parser.feed(text)
            parser.close()
            result = ('\n'.join(parser.nodes) + '\n').encode('utf-8')
    else:
        if type(physical_page) is not int or physical_page < 1:
            raise ValueError('PDF requires a positive, one-based physical page')
        if not body.startswith(b'%PDF-') or pdf_path is None:
            raise ValueError('PDF requires the pinned local PDF response')
        path = Path(pdf_path)
        if path.read_bytes() != body:
            raise ValueError('PDF path differs from the pinned response bytes')
        if not isinstance(tool_version, str) or not tool_version:
            raise ValueError('PDF extraction requires the recorded pdftotext version')
        actual = subprocess.run(['pdftotext', '-v'], check=True, capture_output=True).stderr.decode('utf-8').splitlines()[0]
        if actual != tool_version:
            raise ValueError('pdftotext version differs from the recorded recipe')
        result = subprocess.run(['pdftotext', '-f', str(physical_page), '-l', str(physical_page),
                                 '-layout', '-enc', 'UTF-8', str(path), '-'],
                                check=True, capture_output=True).stdout
        result.decode('utf-8', errors='strict')
    if expected_sha256 is not None:
        _check_digest(result, expected_sha256, 'Derived manifestation')
    return result


def lf_lines(body, start, end):
    """One-based inclusive LF lines, preserving CR, form feeds and empty tails."""
    if type(start) is not int or type(end) is not int or start < 1 or end < start:
        raise ValueError('Invalid one-based LF line range')
    lines = body.decode('utf-8', errors='strict').split('\n')
    if end > len(lines):
        raise ValueError('LF line range lies outside the pinned manifestation')
    return lines[start - 1:end]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--recipe', required=True, choices=KINDS)
    parser.add_argument('--page', type=int)
    parser.add_argument('--tool-version')
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    result = extract(args.source.read_bytes(), args.recipe, source_sha256=args.source_sha256,
                     physical_page=args.page, pdf_path=args.source, tool_version=args.tool_version,
                     expected_sha256=args.expected_sha256)
    # A changed extraction cannot silently overwrite the evidence a reader used.
    if args.output.exists() and args.output.read_bytes() != result:
        raise ValueError('Output exists with different bytes')
    args.output.write_bytes(result)


if __name__ == '__main__':
    main()
