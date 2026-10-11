#!/usr/bin/env python3
"""
Deep comparison tool between generated EPUBs and Gold Standard EPUBs.
Evaluates:
  - File size & package layout
  - Image inventory (count, dimensions, formats)
  - XHTML section structure and headings (h1-h6)
  - Tables, lists, code blocks
  - Complete word count, text alignment, and vocabulary overlap
"""

import os
import sys
import zipfile
import re
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

def analyze_epub(path):
    if not os.path.exists(path):
        return None
    with zipfile.ZipFile(path) as z:
        files = z.namelist()
        xhtml_files = [f for f in files if f.endswith(".xhtml") or f.endswith(".html")]
        img_files = [
            f for f in files 
            if (f.startswith("OEBPS/images/") or f.startswith("GoogleDoc/images/") or f.endswith((".png", ".jpg", ".jpeg", ".gif"))) 
            and not f.startswith("META-INF")
        ]
        
        all_text_tokens = []
        headings = []
        tables = 0
        lists = 0
        
        for xf in sorted(xhtml_files):
            if "toc" in xf.lower() or "nav" in xf.lower():
                continue
            soup = BeautifulSoup(z.read(xf), "html.parser")
            for tag in soup(["script", "style"]):
                tag.decompose()
            t = soup.get_text(separator=" ")
            words = [w for w in re.split(r"\s+", t) if w]
            all_text_tokens.extend(words)
            
            for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                headings.append((h.name, h.get_text().strip()))
            tables += len(soup.find_all("table"))
            lists += len(soup.find_all(["ul", "ol"]))
            
        full_text = " ".join(all_text_tokens)
        file_size = os.path.getsize(path)
        
        return {
            "path": path,
            "file_size": file_size,
            "files_count": len(files),
            "xhtml_count": len(xhtml_files),
            "img_count": len(img_files),
            "img_files": img_files,
            "text_words": len(all_text_tokens),
            "text": full_text,
            "headings": headings,
            "tables": tables,
            "lists": lists,
        }

def compare_epubs(name, gold_path, gen_path):
    print("=" * 70)
    print("COMPARISON: " + name)
    print("=" * 70)
    g = analyze_epub(gold_path)
    m = analyze_epub(gen_path)
    
    if not g:
        print("ERROR: Gold EPUB not found: " + gold_path)
        return
    if not m:
        print("ERROR: Generated EPUB not found: " + gen_path)
        return
    
    print(f"File Size:       Gold={g['file_size']:,} B  |  Ours={m['file_size']:,} B")
    print(f"Images:          Gold={g['img_count']}  |  Ours={m['img_count']}")
    print(f"XHTML Documents: Gold={g['xhtml_count']}  |  Ours={m['xhtml_count']}")
    print(f"Headings Count:  Gold={len(g['headings'])}  |  Ours={len(m['headings'])}")
    print(f"Tables:          Gold={g['tables']}  |  Ours={m['tables']}")
    print(f"Lists:           Gold={g['lists']}  |  Ours={m['lists']}")
    print(f"Total Words:     Gold={g['text_words']}  |  Ours={m['text_words']}")
    
    # Check vocabulary overlap
    words_g = set(re.findall(r"\w+", g["text"].lower()))
    words_m = set(re.findall(r"\w+", m["text"].lower()))
    common_words = words_g & words_m
    vocab_overlap = (len(common_words) / max(len(words_g), 1)) * 100
    print(f"Vocab Overlap:   {vocab_overlap:.2f}% (Gold unique: {len(words_g)}, Ours unique: {len(words_m)})")
    
    # Text SequenceMatcher
    norm_g = re.sub(r"\s+", " ", g["text"]).strip()
    norm_m = re.sub(r"\s+", " ", m["text"]).strip()
    matcher = SequenceMatcher(None, norm_g, norm_m)
    sim = matcher.ratio() * 100
    print(f"Full Text Match: {sim:.2f}%")
    
    # Strip filename header if present in Gold (e.g., Google Docs prepends docx filename)
    filename_stem = os.path.basename(gold_path).replace(".docx.epub", "").replace(".epub", "")
    norm_g_nobanner = norm_g
    for banner in [os.path.basename(gold_path).replace(".epub", ""), filename_stem]:
        norm_g_nobanner = norm_g_nobanner.replace(banner, "").strip()
    
    matcher_content = SequenceMatcher(None, norm_g_nobanner, norm_m)
    print(f"Core Body Match: {matcher_content.ratio() * 100:.2f}% (excluding Google Doc injected file header)")
    
    # Compare headings alignment
    print("\nHeadings Alignment Sample:")
    max_h = max(len(g["headings"]), len(m["headings"]))
    for i in range(min(10, max_h)):
        gh = g["headings"][i] if i < len(g["headings"]) else ("-", "-")
        mh = m["headings"][i] if i < len(m["headings"]) else ("-", "-")
        print(f"  [{i+1:2d}] Gold: <{gh[0]}> {gh[1][:32]:<32} | Ours: <{mh[0]}> {mh[1][:32]}")

if __name__ == "__main__":
    compare_epubs(
        "Lab 5: Transformers",
        "/home/user/Downloads/processed/NLP Lab_5 Transformer_Code_Walkthrough.docx.epub",
        "/tmp/lab5_direct.epub"
    )
    print("\n")
    compare_epubs(
        "Lab 3: Word Embeddings",
        "/home/user/Downloads/processed/NLP Lab 3_ Word Embeddings & Foundational Classifiers.docx.epub",
        "/tmp/lab3_direct.epub"
    )
