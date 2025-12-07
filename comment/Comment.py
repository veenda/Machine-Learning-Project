import os
import csv
import time

from requests import Session, Response
from json import dumps
from dotenv import load_dotenv
from time import sleep
from datetime import datetime
from comment.helpers import logging

class Comment:
    def __init__(self, cookie: str = None) -> None:
        if(not cookie): return logging.error('cookie required !')

        # Inisialisasi Batch
        self.batch_size = 100          
        self.file_counter = 1          
        self.current_batch_data = []   
        self.current_post_id = None

        # Inisialisasi lainnya
        self.__min_id: str =  None

        # Cek apakah ada file checkpoint dari sesi sebelumnya
        if os.path.exists('cursor_checkpoint.txt'):
            try:
                with open('cursor_checkpoint.txt', 'r') as f:
                    saved_cursor = f.read().strip()
                    if saved_cursor:
                        self.__min_id = saved_cursor
                        print(f"[INFO] Ditemukan Checkpoint! Melanjutkan dari cursor: {self.__min_id}")
            except Exception as e:
                print(f"[WARN] Gagal membaca checkpoint: {e}")
        
        self.__result: dict = {}
        self.__result["username"]: str = None
        self.__result["full_name"]: str = None
        self.__result["caption"]: str = None
        self.__result["date_now"]: str = None
        self.__result["create_at"]: str = None
        self.__result["post_url"]: str = None
        self.__result['comments']: list = []
        
        self.__requests : Session = Session()
        self.__requests.headers.update({
            "Cookie": cookie,
            "User-Agent": "Instagram 126.0.0.25.121 Android (23/6.0.1; 320dpi; 720x1280; samsung; SM-A310F; a3xelte; samsungexynos7580; en_GB; 110937453)"
        })

    def __format_date(self, milisecond: int) -> str:
        try:
            return datetime.fromtimestamp(milisecond).strftime("%Y-%m-%dT%H:%M:%S")
        except:
            return datetime.fromtimestamp(milisecond / 1000).strftime("%Y-%m-%dT%H:%M:%S")


    def __dencode_media_id(self, post_id: str) -> int:
        alphabet: str = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        media_id: int = 0

        for char in post_id:
            media_id = media_id * 64 + alphabet.index(char)

        return media_id

    def __build_params(self) -> dict:
        return {
            "can_support_threading": True,
            "sort_order": "popular",
            **({"min_id": self.__min_id} if self.__min_id else {})
        }
    
    def __get_reply_comment(self, comment_id: str):
        min_id: str = ''
        child_comments: list = []
        
        # Loop untuk mengambil semua halaman reply
        while True:
            url = f'https://www.instagram.com/api/v1/media/{self.__media_id}/comments/{comment_id}/child_comments/?min_id={min_id}'
            
            try:
                res_obj = self.__requests.get(url)
                
                # Cek jika status bukan 200 (OK)
                if res_obj.status_code != 200:
                    logging.warning(f"Gagal ambil reply {comment_id}, status: {res_obj.status_code}. Lewati.")
                    break

                response = res_obj.json()
            except Exception as e:
                logging.error(f"Error parsing JSON pada reply {comment_id}: {e}")
                break

            # Jika data child_comments tidak ada, berhenti
            if 'child_comments' not in response:
                break

            child_comments.extend([
                {
                    "username": comment["user"]["username"],
                    "full_name": comment["user"]["full_name"],
                    "comment": comment["text"],
                    "create_time": self.__format_date(comment["created_at"]),
                    "avatar": comment["user"]["profile_pic_url"],
                    "total_like": comment["comment_like_count"],
                } for comment in response['child_comments']
            ])

            if(not response.get('has_more_head_child_comments')): break
            
            min_id: str = response.get('next_min_child_cursor', '')

            # Tambah delay sedikit agar aman dari rate limit
            sleep(2)
            
        return child_comments

    def __filter_comments(self, response: dict) -> None:
        if 'comments' not in response:
            return False

        for comment in response['comments']:
            logging.info(comment['text'])

            comment_obj = {
                "username": comment["user"]["username"],
                "full_name": comment["user"]["full_name"],
                "comment": comment["text"],
                "create_time": self.__format_date(comment["created_at"]),
                "avatar": comment["user"]["profile_pic_url"],
                "total_like": comment["comment_like_count"],
                "total_reply": comment["child_comment_count"],
                # Catatan: replies berbentuk list, di CSV akan tertulis sebagai string list
                "replies": self.__get_reply_comment(comment['pk']) if comment['child_comment_count'] else [] 
            }

            self.__result['comments'].append(comment_obj)
            
            # Logika Batch Insert
            self.current_batch_data.append(comment_obj) # Masukkan ke list batch

            # Cek jika sudah mencapai 100
            if len(self.current_batch_data) == self.batch_size:
                self.__save_batch_to_csv()
            
            sleep(1)

        if (not 'next_min_id' in response): return True 

        self.__min_id = response['next_min_id'] 

        
    def excecute(self, post_id: str):
        self.__media_id = self.__dencode_media_id(post_id)
        while(True):
            try:
                res_obj = self.__requests.get(f'https://www.instagram.com/api/v1/media/{self.__media_id}/comments/', params=self.__build_params())

                if(res_obj.status_code != 200): 
                    logging.error(f"Gagal mengambil komentar utama. Status: {res_obj.status_code}")
                    return self.__result # Kembalikan apa yang sudah didapat

                data: dict = res_obj.json() 

                if(not self.__result['comments']): 
                    logging.info('Berhasil mengambil metadata post.')
                    # Handle jika caption kosong atau struktur beda
                    caption_node = data.get("caption")
                    if caption_node:
                        self.__result["username"]: str = caption_node["user"]["username"]
                        self.__result["full_name"]: str = caption_node["user"]["full_name"]
                        self.__result["caption"]: str = caption_node["text"]
                        self.__result["create_at"]: str = self.__format_date(caption_node["created_at"])
                    
                    self.__result["date_now"]: str = self.__format_date(round(time.time() * 1000))
                    self.__result["post_url"]: str = f"https://instagram.com/p/{post_id}"

                if(self.__filter_comments(data)): break
            
            except Exception as e:
                logging.error(f"Error pada loop utama excecute: {e}")
                break
        
        return self.__result
    
    # Penyimpan CSV
    def __save_batch_to_csv(self):
        if not self.current_batch_data:
            return

        # Pastikan folder 'data' ada (sesuai output default di main.py)
        if not os.path.exists('data'):
            os.makedirs('data')

        # Nama file: data/IDPOSTINGAN_1.csv, data/IDPOSTINGAN_2.csv, dst
        filename = f"data/{self.current_post_id}_{self.file_counter}.csv"
        
        # Ambil keys dari data pertama untuk header
        keys = self.current_batch_data[0].keys()

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(self.current_batch_data)
            
            print(f"[INFO] Berhasil menyimpan batch ke-{self.file_counter} ke {filename}")
            
            # Reset batch dan naikkan counter
            self.file_counter += 1
            self.current_batch_data = []
            
        except Exception as e:
            print(f"[ERROR] Gagal menyimpan batch CSV: {e}")
    # ---------------------------------------


if(__name__ == '__main__'):
    load_dotenv() 
    cookie = os.getenv("COOKIE") 
    comment: Comment = Comment(cookie)
    # data: dict = comment.excecute('Cm2cJmABD1p')