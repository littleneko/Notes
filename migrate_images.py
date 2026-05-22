#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import concurrent.futures
import hashlib
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# --- Regex patterns ---

MD_IMG_RE = re.compile(
    r'!\[([^\]]*)\]'      # ![alt]
    r'\('                  # (
    r'(https?://[^ )]+)'  # url
    r'\)'                  # )
)

HTML_IMG_RE = re.compile(
    r'<img\s+'
    r'([^>]*?)'            # pre-src attributes
    r'src="(https?://[^"]+)"'  # src="url"
    r'([^>]*?)'            # post-src attributes
    r'/?>'                 # /> or >
)

CONTENT_TYPE_TO_EXT = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/svg+xml': '.svg',
    'image/bmp': '.bmp',
    'image/x-icon': '.ico',
}

USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


# --- Data structures ---

@dataclass
class ImageMatch:
    md_file: str
    url: str
    clean_url: str
    domain: str
    match_text: str
    pre_src: str
    post_src: str


# --- Scanning ---

def canonicalize_url(raw_url):
    parsed = urlparse(raw_url)
    clean = urlunparse(parsed._replace(fragment=''))
    return clean, parsed.fragment


def scan_markdown_files(project_root):
    all_matches = []
    md_files = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.lower().endswith('.md'):
                md_files.append(os.path.join(root, f))

    for md_file in md_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as fh:
                content = fh.read()
        except (OSError, UnicodeDecodeError):
            continue

        for match in MD_IMG_RE.finditer(content):
            url = match.group(2)
            clean_url, _ = canonicalize_url(url)
            domain = urlparse(url).netloc
            all_matches.append(ImageMatch(
                md_file=md_file,
                url=url,
                clean_url=clean_url,
                domain=domain,
                match_text=match.group(0),
                pre_src='',
                post_src='',
            ))

        for match in HTML_IMG_RE.finditer(content):
            pre = match.group(1)
            url = match.group(2)
            post = match.group(3)
            clean_url, _ = canonicalize_url(url)
            domain = urlparse(url).netloc
            all_matches.append(ImageMatch(
                md_file=md_file,
                url=url,
                clean_url=clean_url,
                domain=domain,
                match_text=match.group(0),
                pre_src=pre,
                post_src=post,
            ))

    return all_matches


# --- stats subcommand ---

def cmd_stats(args):
    project_root = get_project_root()
    matches = scan_markdown_files(project_root)

    domain_counts = defaultdict(int)
    file_domain_counts = defaultdict(lambda: defaultdict(int))

    for m in matches:
        domain_counts[m.domain] += 1
        file_domain_counts[m.md_file][m.domain] += 1

    files_with_images = len(file_domain_counts)

    if args.by_file:
        for md_file in sorted(file_domain_counts.keys()):
            rel = os.path.relpath(md_file, project_root)
            print(rel)
            total = 0
            for domain, count in sorted(file_domain_counts[md_file].items(), key=lambda x: -x[1]):
                print(f"  {domain}  {count}")
                total += count
            print(f"  Total: {total}\n")
    else:
        print("Domain statistics:")
        for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
            print(f"  {domain}  {count}")

    total = sum(domain_counts.values())
    print(f"\nTotal: {total} image links across {files_with_images} files")


# --- list subcommand ---

def cmd_list(args):
    project_root = get_project_root()
    matches = scan_markdown_files(project_root)

    if args.domain:
        matches = [m for m in matches if args.domain in m.domain]

    if args.by_file:
        file_urls = defaultdict(list)
        for m in matches:
            file_urls[m.md_file].append(m.url)

        for md_file in sorted(file_urls.keys()):
            rel = os.path.relpath(md_file, project_root)
            print(rel)
            for url in file_urls[md_file]:
                print(f"  {url}")
            print(f"  ({len(file_urls[md_file])} links)\n")
    else:
        seen = set()
        for m in matches:
            if m.clean_url not in seen:
                seen.add(m.clean_url)
                print(m.clean_url)
        print(f"\nTotal: {len(seen)} unique URLs")


# --- migrate subcommand ---

def derive_filename(url, output_dir):
    parsed = urlparse(url)
    path = parsed.path
    basename = os.path.basename(path)

    # OSS pattern: /img/xxx -> use xxx
    if path.startswith('/img/'):
        basename = path[len('/img/'):]

    # If basename is empty (path ends with /), use a hash
    if not basename:
        basename = hashlib.md5(url.encode()).hexdigest()[:16]

    return basename


def resolve_filename(basename, url, existing_basenames):
    if basename not in existing_basenames:
        existing_basenames.add(basename)
        return basename

    name, ext = os.path.splitext(basename)
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    new_name = f"{name}_{h}{ext}"
    existing_basenames.add(new_name)
    return new_name


def download_image(url, dest_path, timeout, skip_existing=True):
    if skip_existing and os.path.exists(dest_path):
        return True, None

    req = Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            content_type = resp.headers.get('Content-Type', '').split(';')[0].strip()
            with open(dest_path, 'wb') as f:
                f.write(data)
            return True, content_type
    except Exception as e:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False, str(e)


def relative_path_from_md(md_file, project_root, output_dir, local_filename):
    image_abs = os.path.join(project_root, output_dir, local_filename)
    md_dir = os.path.dirname(md_file)
    return os.path.relpath(image_abs, md_dir)


def cmd_migrate(args):
    project_root = get_project_root()
    matches = scan_markdown_files(project_root)

    target_matches = [m for m in matches if args.domain in m.domain]
    if not target_matches:
        print(f"No image links found for domain: {args.domain}")
        return

    # Build url -> local filename mapping
    url_to_localname = {}
    existing_basenames = set()
    for m in target_matches:
        if m.clean_url not in url_to_localname:
            raw_name = derive_filename(m.clean_url, args.output_dir)
            final_name = resolve_filename(raw_name, m.clean_url, existing_basenames)
            url_to_localname[m.clean_url] = final_name

    output_path = os.path.join(project_root, args.output_dir)
    os.makedirs(output_path, exist_ok=True)

    if args.dry_run:
        print(f"Dry run: would download {len(url_to_localname)} images to {args.output_dir}/")
        print(f"Would update {len(set(m.md_file for m in target_matches))} .md files")
        for url, localname in sorted(url_to_localname.items(), key=lambda x: x[1]):
            print(f"  {localname} <- {url}")
        return

    # Download
    download_tasks = []
    for url, localname in url_to_localname.items():
        dest = os.path.join(output_path, localname)
        if os.path.exists(dest):
            print(f"  Skipped (exists): {localname}")
            continue
        download_tasks.append((url, dest, localname))

    failed_downloads = set()
    completed = 0
    total_tasks = len(download_tasks)

    if download_tasks:
        print(f"Downloading {total_tasks} images ({args.workers} workers)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_info = {}
            for url, dest, localname in download_tasks:
                future = executor.submit(download_image, url, dest, args.timeout)
                future_to_info[future] = (url, dest, localname)

            for future in concurrent.futures.as_completed(future_to_info):
                url, dest, localname = future_to_info[future]
                success, result = future.result()
                completed += 1
                if success:
                    # Handle extensionless files using Content-Type
                    name, ext = os.path.splitext(localname)
                    if not ext and result:
                        new_ext = CONTENT_TYPE_TO_EXT.get(result, '.png')
                        new_name = localname + new_ext
                        new_dest = os.path.join(output_path, new_name)
                        os.rename(dest, new_dest)
                        url_to_localname[url] = new_name
                    print(f"  [{completed}/{total_tasks}] Downloaded: {localname}")
                else:
                    failed_downloads.add(url)
                    print(f"  [{completed}/{total_tasks}] FAILED: {url} - {result}")

    # Check for extensionless files that were skipped (already existed)
    for url, localname in url_to_localname.items():
        dest = os.path.join(output_path, localname)
        name, ext = os.path.splitext(localname)
        if not ext and os.path.exists(dest):
            # Already downloaded previously, try to detect extension from Content-Type
            # For skipped files, we just add a default extension
            new_name = localname + '.png'
            new_dest = os.path.join(output_path, new_name)
            if not os.path.exists(new_dest):
                os.rename(dest, new_dest)
                url_to_localname[url] = new_name

    if failed_downloads:
        print(f"\n{len(failed_downloads)} downloads failed")

    # Rewrite .md files
    files_to_rewrite = set(m.md_file for m in target_matches)
    rewritten = 0
    skipped = 0

    print(f"\nRewriting {len(files_to_rewrite)} .md files...")
    for md_file in sorted(files_to_rewrite):
        file_matches = [m for m in target_matches if m.md_file == md_file]
        # Skip file if any URL in it failed to download
        if any(m.clean_url in failed_downloads for m in file_matches):
            skipped += 1
            rel = os.path.relpath(md_file, project_root)
            print(f"  Skipped (has failed downloads): {rel}")
            continue

        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            continue

        # Replace markdown images
        def md_replacer(match):
            url = match.group(2)
            clean_url, _ = canonicalize_url(url)
            if clean_url not in url_to_localname:
                return match.group(0)
            localname = url_to_localname[clean_url]
            rel_path = relative_path_from_md(md_file, project_root, args.output_dir, localname)
            alt = match.group(1)
            return f'![{alt}]({rel_path})'

        new_content = MD_IMG_RE.sub(md_replacer, content)

        # Replace HTML img tags
        def html_replacer(match):
            pre = match.group(1)
            url = match.group(2)
            post = match.group(3)
            clean_url, _ = canonicalize_url(url)
            if clean_url not in url_to_localname:
                return match.group(0)
            localname = url_to_localname[clean_url]
            rel_path = relative_path_from_md(md_file, project_root, args.output_dir, localname)
            return f'<img {pre}src="{rel_path}"{post}/>'

        new_content = HTML_IMG_RE.sub(html_replacer, new_content)

        if new_content != content:
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            rel = os.path.relpath(md_file, project_root)
            print(f"  Updated: {rel}")
            rewritten += 1

    if skipped:
        print(f"\n{skipped} files skipped (had failed downloads)")
    print(f"\nDone. {rewritten} files updated.")


# --- Utilities ---

def get_project_root():
    return os.path.dirname(os.path.abspath(__file__))


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description='Markdown image migration tool')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # stats
    stats_parser = subparsers.add_parser('stats', help='Show image domain statistics')
    stats_parser.add_argument('--by-file', action='store_true', help='Show stats per .md file')

    # list
    list_parser = subparsers.add_parser('list', help='List image URLs')
    list_parser.add_argument('--by-file', action='store_true', help='Group by .md file')
    list_parser.add_argument('--domain', type=str, help='Filter by domain')

    # migrate
    migrate_parser = subparsers.add_parser('migrate', help='Download images and rewrite links')
    migrate_parser.add_argument('--domain', required=True, help='Target domain')
    migrate_parser.add_argument('--output-dir', required=True, help='Local directory for images')
    migrate_parser.add_argument('--dry-run', action='store_true', help='Scan only, no download/rewrite')
    migrate_parser.add_argument('--workers', type=int, default=4, help='Download threads')
    migrate_parser.add_argument('--timeout', type=int, default=30, help='HTTP timeout in seconds')

    args = parser.parse_args()

    if args.command == 'stats':
        cmd_stats(args)
    elif args.command == 'list':
        cmd_list(args)
    elif args.command == 'migrate':
        cmd_migrate(args)


if __name__ == '__main__':
    main()
