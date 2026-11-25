"""Runs every demo and prints a numbered list of the tools and of the files the demos produced."""
import asyncio, pathlib, runpy, sys, time

here = pathlib.Path(__file__).parent
from uiforge_mcp import server as s

tools = asyncio.run(s.mcp.list_tools())
print(f"== {len(tools)} tool ==")
for i, t in enumerate(sorted(tools, key=lambda t: t.name), 1):
    print(f"{i:2}. {t.name:24} {(t.description or '').strip().splitlines()[0][:90]}")

start = time.time()
for demo in sorted(here.glob("demo*.py")):
    print(f"\n-> {demo.name} calisiyor...")
    sys.argv = [str(demo)]
    runpy.run_path(str(demo), run_name="__main__")

print("\n== uretilen dosyalar ==")
made = [p for p in sorted(here.iterdir()) if p.is_file() and p.stat().st_mtime >= start]
for i, p in enumerate(made, 1):
    print(f"{i:2}. {p.name:28} {p.stat().st_size // 1024} KB")
