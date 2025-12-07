def __init__(self, cookie: str = None) -> None:
        if(not cookie): return logging.error('cookie required !')

        # --- TAMBAHAN UNTUK BATCH CSV ---
        self.batch_size = 100          # Jumlah data per file
        self.file_counter = 1          # Counter nama file (1, 2, 3...)
        self.current_batch_data = []   # Penampung sementara
        self.current_post_id = None    # Untuk nama file
        # --------------------------------

        self.__min_id: str =  None
        # ... (kode lainnya) ...