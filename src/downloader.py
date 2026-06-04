#!/usr/bin/env python3
"""
Feishu Spreadsheet Media Batch Downloader

Automatically extracts attachments (video/images) from Feishu spreadsheets
and downloads them in bulk. Designed for film production workflows where
shot lists with embedded media need to be distributed to editors.

Usage:
    python downloader.py --token <user_access_token>

Requires a Feishu user_access_token obtained via OAuth device flow.
See README for the full authentication guide.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FEISHU_BASE = "https://open.feishu.cn/open-apis"


# ---------------------------------------------------------------------------
# Spreadsheet Reader
# ---------------------------------------------------------------------------
def read_spreadsheet(spreadsheet_token: str, sheet_id: str, token: str) -> list:
    """分页读取电子表格全部数据"""
    all_values = []
    page_size = 100
    offset = 0

    while True:
        start = offset + 1
        end = offset + page_size
        url = (
            f"{FEISHU_BASE}/sheets/v2/spreadsheets/{spreadsheet_token}"
            f"/values/{sheet_id}!A{start}:Z{end}"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp = requests.get(url, headers=headers, timeout=30)
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"读取表格失败: {data.get('msg')} (code={data.get('code')})")

        values = data.get("data", {}).get("valueRange", {}).get("values", [])
        if not values:
            break

        all_values.extend(values)

        if len(values) < page_size:
            break

        offset += page_size
        time.sleep(0.2)  # rate limiting

    return all_values


# ---------------------------------------------------------------------------
# Attachment Extractor
# ---------------------------------------------------------------------------
def extract_attachments(rows: list, column_keyword: str = "分镜视频") -> list:
    """
    从表格行中提取所有附件

    参数:
        rows: 表格数据，第一行为表头
        column_keyword: 用于识别目标列的关键词（如"分镜视频"）

    返回:
        [{"file_token": ..., "name": ..., "size": ..., "scene": ..., "shot": ...}, ...]
    """
    if not rows:
        return []

    headers = rows[0]

    # Find columns matching the keyword
    target_cols = []
    for i, header in enumerate(headers):
        if header and column_keyword in str(header):
            target_cols.append(i)

    if not target_cols:
        print(f"⚠️  未找到包含「{column_keyword}」的列", file=sys.stderr)

    attachments = []

    for row in rows[1:]:
        scene = str(row[0]) if len(row) > 0 and row[0] else ""
        shot = str(row[1]) if len(row) > 1 and row[1] else ""

        for col in target_cols:
            if col >= len(row):
                continue
            cell = row[col]
            if cell is None or cell in ("—", ""):
                continue

            # Feishu attachment: cell may contain list of {fileToken, text, type:"attachment"}
            if isinstance(cell, list):
                for item in cell:
                    if isinstance(item, dict) and item.get("type") == "attachment":
                        file_token = item.get("fileToken")
                        if file_token:
                            attachments.append({
                                "file_token": file_token,
                                "name": item.get("text", "unknown"),
                                "size": item.get("size", 0),
                                "scene": scene,
                                "shot": shot,
                            })
            elif isinstance(cell, dict) and cell.get("type") == "attachment":
                # Single attachment
                file_token = cell.get("fileToken") or cell.get("file_token")
                if file_token:
                    attachments.append({
                        "file_token": file_token,
                        "name": cell.get("text", cell.get("name", "unknown")),
                        "size": cell.get("size", 0),
                        "scene": scene,
                        "shot": shot,
                    })

    return attachments


# ---------------------------------------------------------------------------
# Media Downloader
# ---------------------------------------------------------------------------
def download_media(token: str, file_token: str, name: str, output_dir: Path) -> bool:
    """下载单个文件"""
    url = f"{FEISHU_BASE}/drive/v1/medias/{file_token}/download"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=120)

        if resp.status_code != 200:
            print(f"  ❌ {name} (HTTP {resp.status_code})", file=sys.stderr)
            return False

        # Handle filename collisions
        output_path = output_dir / name
        base, ext = os.path.splitext(name)
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{base}_{counter}{ext}"
            counter += 1

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"  ✅ {output_path.name} ({size_mb:.1f} MB)")
        return True

    except requests.RequestException as e:
        print(f"  ❌ {name} ({e})", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="飞书电子表格媒体文件批量下载",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python downloader.py -t <token> -s XdTqsCxxxx -o ./videos

认证流程详见 README。
        """,
    )
    parser.add_argument("-t", "--token", required=True, help="飞书 User Access Token")
    parser.add_argument(
        "-s", "--spreadsheet",
        default=os.environ.get("FEISHU_SHEET_TOKEN", ""),
        help="电子表格 token（从 URL 提取）",
    )
    parser.add_argument(
        "--sheet-id",
        default="1",
        help="工作表 ID（默认 1）",
    )
    parser.add_argument(
        "-o", "--output",
        default="./downloads",
        help="输出目录 (默认: ./downloads)",
    )
    parser.add_argument(
        "-c", "--column",
        default="分镜视频",
        help="目标列关键词 (默认: 分镜视频)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出文件，不下载",
    )

    args = parser.parse_args()

    if not args.spreadsheet:
        parser.error("请通过 -s 或环境变量 FEISHU_SHEET_TOKEN 指定电子表格 token")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📋 正在读取电子表格 {args.spreadsheet}...", file=sys.stderr)
    rows = read_spreadsheet(args.spreadsheet, args.sheet_id, args.token)
    print(f"   共 {len(rows)} 行数据", file=sys.stderr)

    attachments = extract_attachments(rows, column_keyword=args.column)
    print(f"🎬 找到 {len(attachments)} 个可下载的文件\n", file=sys.stderr)

    if args.dry_run:
        for a in attachments:
            size_mb = a["size"] / 1024 / 1024
            print(f"   [{a['scene']}-{a['shot']}] {a['name']} ({size_mb:.1f} MB)")
        return

    success = 0
    failed = 0
    for i, a in enumerate(attachments, 1):
        size_mb = a["size"] / 1024 / 1024
        print(f"[{i}/{len(attachments)}] [{a['scene']}-{a['shot']}] {a['name']} ({size_mb:.1f} MB)",
              file=sys.stderr)
        if download_media(args.token, a["file_token"], a["name"], output_dir):
            success += 1
        else:
            failed += 1

    print(f"\n🎉 完成！成功 {success}/{len(attachments)}，失败 {failed}，保存在 {output_dir}/",
          file=sys.stderr)


if __name__ == "__main__":
    main()
