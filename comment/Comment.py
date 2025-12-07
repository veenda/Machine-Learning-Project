import os
import csv
import glob
import shutil
import requests 
from requests import Session, Response
from json import dumps
from dotenv import load_dotenv
from time import sleep, time
from datetime import datetime
from comment.helpers import logging
from requests.exceptions import JSONDecodeError 

class Comment:
    def __init__(self, cookie: str = None) -> None:
        if(not cookie): return logging.error('cookie required !')

        # --- KONFIGURASI ---
        self.batch_size = 100               # 100 Data per file
        self.cursor_folder = "cursor"       # Folder Checkpoint
        self.dataset_base_folder = "datasets" # Folder Data
        
        # Buat folder jika belum ada
        os.makedirs(self.cursor_folder, exist_ok=True)
        os.makedirs(self.dataset_base_folder, exist_ok=True)
        
        self.current_batch_data = []       
        self.current_post_id = None        
        self.target_folder = None          
        self.checkpoint_file = None        
        self.file_counter = 1              

        self.__min_id: str =  None
        
        self.__result: dict = {}
        self.__result["username"]: str = None
        self.__result["full_name"]: str = None
        self.__result["caption"]: str = None
        self.__result["date_now"]: str = None
        self.__result["create_at"]: str = None
        self.__result["post_url"]: str = None
        self.__result['comments']: list = []
        
        self.__requests : Session = Session()
        # BERSIHKAN COOKIE DARI ENTER/SPASI
        clean_cookie = cookie.strip().replace('\n', '').replace('\r', '')
        self.__requests.headers.update({
            "Cookie": clean_cookie,
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
    
    # --- BAGIAN YANG DIPERBAIKI (ANTI CRASH) ---
    def __get_reply_comment(self, comment_id: str):
        min_id: str = ''
        child_comments: list = []

        while True:
            try:
                # JANGAN LANGSUNG .json() DI SINI!
                response = self.__requests.get(f'https://www.instagram.com/api/v1/media/{self.__media_id}/comments/{comment_id}/child_comments/?min_id={min_id}')
                
                # 1. Cek Status Code
                if response.status_code == 429:
                    logging.warning("Rate Limit (429) di Reply. Tidur 60 detik...")
                    sleep(60)
                    continue
                elif response.status_code != 200:
                    logging.warning(f"Gagal reply (Status {response.status_code}). Skip.")
                    return child_comments 
                
                # 2. Cek apakah isinya JSON valid
                try:
                    data = response.json()
                except JSONDecodeError:
                    if 'login' in response.text.lower():
                        logging.error("Cookie Expired saat ambil reply. Berhenti total.")
                        raise requests.exceptions.RequestException("CRITICAL: Cookie Invalid")
                    else:
                        logging.warning("Respon server aneh (Bukan JSON). Retrying...")
                        sleep(2)
                        continue

            except requests.exceptions.RequestException as e:
                if "CRITICAL" in str(e): raise 
                logging.warning(f"Koneksi error di reply: {e}. Retrying...")
                sleep(2)
                continue
            
            if 'child_comments' not in data: break

            child_comments.extend([
                {
                    "username": comment["user"]["username"],
                    "full_name": comment["user"]["full_name"],
                    "comment": comment["text"],
                    "create_time": self.__format_date(comment["created_at"]),
                    "avatar": comment["user"]["profile_pic_url"],
                    "total_like": comment["comment_like_count"],
                } for comment in data.get('child_comments', [])
            ])

            if(not data.get('has_more_head_child_comments')): break
            
            min_id: str = data.get('next_min_child_cursor', '')
            sleep(1)
        return child_comments

    def __migrate_old_data(self, post_id):
        old_folders = ['data', 'data_tes', '.'] 
        moved_count = 0
        for folder in old_folders:
            pattern = os.path.join(folder, f"*{post_id}*.csv")
            for old_file in glob.glob(pattern):
                if os.path.abspath(old_file) == os.path.abspath(self.target_folder): continue
                filename = os.path.basename(old_file)
                new_path = os.path.join(self.target_folder, filename)
                try:
                    if not os.path.exists(new_path):
                        shutil.move(old_file, new_path)
                        logging.info(f"[MIGRASI] Memindahkan {filename} ke {self.target_folder}")
                        moved_count += 1
                except: pass

    def __save_batch_to_csv(self):
        if not self.current_batch_data: return
        filename = f"{self.current_post_id}_{self.file_counter}.csv"
        filepath = os.path.join(self.target_folder, filename)
        keys = self.current_batch_data[0].keys()
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(self.current_batch_data)
            logging.info(f"[SAVED] Batch ke-{self.file_counter} disimpan: {filename} ({len(self.current_batch_data)} data)")
            self.file_counter += 1
            self.current_batch_data = []
        except Exception as e:
            logging.error(f"[ERROR] Gagal simpan CSV: {e}")

    def __filter_comments(self, response: dict) -> None:
        if 'comments' not in response: return True

        for comment in response['comments']:
            comment_obj = {
                "username": comment["user"]["username"],
                "full_name": comment["user"]["full_name"],
                "comment": comment["text"],
                "create_time": self.__format_date(comment["created_at"]),
                "avatar": comment["user"]["profile_pic_url"],
                "total_like": comment["comment_like_count"],
                "total_reply": comment["child_comment_count"],
                "replies": self.__get_reply_comment(comment['pk']) if comment['child_comment_count'] else [] 
            }
            self.__result['comments'].append(comment_obj) 
            self.current_batch_data.append(comment_obj)

            if len(self.current_batch_data) >= self.batch_size:
                self.__save_batch_to_csv()
            sleep(0.5)

        if (not 'next_min_id' in response): return True 
        self.__min_id = response['next_min_id'] 

        try:
            with open(self.checkpoint_file, 'w') as f:
                f.write(self.__min_id)
        except: pass
        
    def excecute(self, post_id: str):
        self.__media_id = self.__dencode_media_id(post_id)
        self.current_post_id = post_id
        
        # Setup Folder & Migrasi
        self.target_folder = os.path.join(self.dataset_base_folder, post_id)
        os.makedirs(self.target_folder, exist_ok=True)
        self.__migrate_old_data(post_id)
        
        # Setup File Counter
        existing_files = glob.glob(os.path.join(self.target_folder, "*.csv"))
        self.file_counter = len(existing_files) + 1 if existing_files else 1

        # Setup Checkpoint
        self.checkpoint_file = os.path.join(self.cursor_folder, f"checkpoint_{self.__media_id}.txt")
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    self.__min_id = f.read().strip()
                    logging.info(f"[RESUME] Melanjutkan {post_id} dari: {self.__min_id}")
            except: pass

        logging.info(f"--- Memulai Scraping {post_id} ---")

        while(True):
            try:
                response = self.__requests.get(f'https://www.instagram.com/api/v1/media/{self.__media_id}/comments/', params=self.__build_params())
                
                if response.status_code == 429:
                    logging.warning("Rate Limit (429). Tidur 60 detik...")
                    sleep(60)
                    continue
                
                # Cek JSON Utama
                try:
                    data: dict = response.json() 
                except JSONDecodeError:
                    if 'login' in response.text.lower():
                        logging.error("Cookie Invalid/Expired. Berhenti.")
                        return 
                    else:
                        logging.error(f"Gagal parse JSON utama (Status {response.status_code}).")
                        return

                if(not self.__result.get('post_url')): 
                    try:
                        self.__result["username"] = data["caption"]["user"]["username"]
                        self.__result["full_name"] = data["caption"]["user"]["full_name"]
                        self.__result["caption"] = data["caption"]["text"]
                        self.__result["date_now"] = self.__format_date(round(time() * 1000))
                        self.__result["create_at"] = self.__format_date(data["caption"]["created_at"])
                        self.__result["post_url"] = f"https://instagram.com/p/{post_id}"
                    except: pass 

                is_done = self.__filter_comments(data)
                if is_done: 
                    logging.info(f"--- Selesai {post_id} ---")
                    break
            
            except Exception as e:
                logging.error(f"Error loop utama: {e}")
                if "CRITICAL" in str(e): break
                sleep(5) 
        
        if len(self.current_batch_data) > 0:
            self.__save_batch_to_csv()
        
        return self.__result