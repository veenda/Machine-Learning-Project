import os
import re
import csv  # Import library csv
from argparse import ArgumentParser

from comment import Comment
from comment.helpers import logging

if(__name__ == '__main__'):
    argp: ArgumentParser = ArgumentParser()
    argp.add_argument("--url", '-u', type=str, default='Cm2cJmABD1p')
    argp.add_argument("--cookie", '-c', type=str)
    argp.add_argument("--output", '-o', type=str, default='data')
    args = argp.parse_args()

    # Ekstrak Post ID dari URL
    post_id: str = (match := re.compile(r'https://www\.instagram\.com/(p|reel)/([^/?]+)|([^/]+)$').search(args.url)) and (match.group(2) or match.group(3)) 

    comment: Comment = Comment(args.cookie)

    if(not os.path.exists(args.output)):
            os.makedirs(args.output)
    
    # Eksekusi scraping
    result_data = comment.excecute(post_id)
    
    # Ambil waktu scraping dari root object result
    scraped_at = result_data.get("date_now", "")

    # Tentukan nama file output CSV
    output_filename = f'{args.output}/{post_id}.csv'

    with open(output_filename, 'w', newline='', encoding='utf-8') as csvfile:
        # Definisi nama kolom
        fieldnames = ['scraped_at', 'created_at', 'username', 'comment', 'likes']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Tulis Header
        writer.writeheader()

        # Iterasi setiap komentar utama
        for c in result_data.get('comments', []):
            # 1. Tulis Komentar Utama
            writer.writerow({
                'scraped_at': scraped_at,         # Kapan discraping
                'created_at': c['create_time'],   # Kapan dibuat
                'username': c['username'],        # Isi Komentar
                'comment': c['comment'],          # Username
                'likes': c['total_like']          # Jumlah Like
            })

            # 2. Tulis Reply/Balasan (jika ada)
            if 'replies' in c and c['replies']:
                for reply in c['replies']:
                    writer.writerow({
                        'scraped_at': scraped_at,
                        'created_at': reply['create_time'],
                        'username': reply['username'],
                        'comment': reply['comment'],
                        'likes': reply['total_like']
                    })

        logging.info(f'Output data saved to: {output_filename}')