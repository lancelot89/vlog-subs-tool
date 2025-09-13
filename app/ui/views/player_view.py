"""
動画プレイヤービューの実装
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QCheckBox, QGroupBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap, QPainter, QPen
import cv2
import numpy as np
from pathlib import Path


class PlayerView(QWidget):
    """動画プレイヤービューウィジェット"""
    
    # シグナル定義
    time_changed = Signal(int)  # 再生時間変更（ミリ秒）
    frame_changed = Signal(int)  # フレーム変更
    subtitle_sync_request = Signal(int)  # 字幕同期要求
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cap = None
        self.current_frame = 0
        self.total_frames = 0
        self.fps = 30.0
        self.current_time_ms = 0
        
        # 字幕関連
        self.current_subtitles = []
        self.current_subtitle_text = ""
        
        # ループ再生関連
        self.loop_start_ms = 0
        self.loop_end_ms = 0
        self.is_looping = False
        
        # タイマー
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        
        self.init_ui()
    
    def init_ui(self):
        """UIの初期化"""
        layout = QVBoxLayout(self)
        
        # 動画表示エリア
        self.video_label = QLabel()
        self.video_label.setMinimumSize(400, 300)
        self.video_label.setStyleSheet("border: 1px solid gray; background-color: black;")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setText("動画をドラッグ&ドロップするか、\\n「動画を開く」ボタンから読み込んでください")
        layout.addWidget(self.video_label)
        
        # 再生コントロール
        control_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("再生")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)
        control_layout.addWidget(self.play_btn)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        
        control_layout.addStretch()
        
        # 時間表示
        self.time_label = QLabel("00:00:00 / 00:00:00")
        control_layout.addWidget(self.time_label)
        
        layout.addLayout(control_layout)
        
        # シークバー
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.valueChanged.connect(self.seek_to_frame)
        layout.addWidget(self.seek_slider)
        
        # 表示オプション
        options_group = QGroupBox("表示オプション")
        options_layout = QHBoxLayout(options_group)
        
        self.show_roi_check = QCheckBox("抽出領域枠表示")
        self.show_roi_check.toggled.connect(self.update_display)
        options_layout.addWidget(self.show_roi_check)
        
        self.show_subtitle_check = QCheckBox("字幕オーバーレイ")
        self.show_subtitle_check.toggled.connect(self.update_display)
        options_layout.addWidget(self.show_subtitle_check)
        
        options_layout.addStretch()
        
        layout.addWidget(options_group)
        
        # 区間ループ設定
        loop_group = QGroupBox("区間ループ")
        loop_layout = QHBoxLayout(loop_group)
        
        self.loop_check = QCheckBox("ループ再生")
        loop_layout.addWidget(self.loop_check)
        
        self.loop_start_btn = QPushButton("開始点設定")
        self.loop_start_btn.setEnabled(False)
        self.loop_start_btn.clicked.connect(self.set_loop_start)
        loop_layout.addWidget(self.loop_start_btn)
        
        self.loop_end_btn = QPushButton("終了点設定")
        self.loop_end_btn.setEnabled(False)
        self.loop_end_btn.clicked.connect(self.set_loop_end)
        loop_layout.addWidget(self.loop_end_btn)
        
        self.clear_loop_btn = QPushButton("解除")
        self.clear_loop_btn.setEnabled(False)
        self.clear_loop_btn.clicked.connect(self.clear_loop)
        loop_layout.addWidget(self.clear_loop_btn)
        
        loop_layout.addStretch()
        
        layout.addWidget(loop_group)
    
    def load_video(self, file_path: str):
        """動画を読み込む"""
        try:
            if self.cap:
                self.cap.release()
            
            self.cap = cv2.VideoCapture(file_path)
            if not self.cap.isOpened():
                raise Exception("動画ファイルを開けませんでした")
            
            # 動画情報の取得
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            # UIの更新
            self.seek_slider.setRange(0, self.total_frames - 1)
            self.seek_slider.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
            self.loop_start_btn.setEnabled(True)
            self.loop_end_btn.setEnabled(True)
            
            # 最初のフレームを表示
            self.seek_to_frame(0)
            
        except Exception as e:
            print(f"動画読み込みエラー: {e}")
    
    def toggle_play(self):
        """再生/一時停止の切り替え"""
        if self.timer.isActive():
            self.timer.stop()
            self.play_btn.setText("再生")
        else:
            if self.cap and self.cap.isOpened():
                interval = int(1000 / self.fps)  # ミリ秒
                self.timer.start(interval)
                self.play_btn.setText("一時停止")
    
    def stop(self):
        """停止"""
        self.timer.stop()
        self.play_btn.setText("再生")
        self.seek_to_frame(0)
    
    def seek_to_frame(self, frame_num: int):
        """指定フレームにシーク"""
        if not self.cap or not self.cap.isOpened():
            return
        
        self.current_frame = frame_num
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        
        # 時間の計算
        self.current_time_ms = int(frame_num * 1000 / self.fps)
        
        # フレームの読み込みと表示
        ret, frame = self.cap.read()
        if ret:
            self.display_frame(frame)
        
        # 字幕更新
        self.update_current_subtitle()
        
        # シグナルの発信
        self.time_changed.emit(self.current_time_ms)
        self.frame_changed.emit(frame_num)
        
        # 時間表示の更新
        self.update_time_display()
    
    def seek_to_time(self, time_ms: int):
        """指定時間にシーク"""
        frame_num = int(time_ms * self.fps / 1000)
        if 0 <= frame_num < self.total_frames:
            self.seek_slider.setValue(frame_num)
            self.seek_to_frame(frame_num)
    
    def update_frame(self):
        """フレーム更新（再生時）"""
        if not self.cap or not self.cap.isOpened():
            return
        
        next_frame = self.current_frame + 1
        next_time_ms = int(next_frame * 1000 / self.fps)
        
        # ループ再生チェック
        if self.loop_check.isChecked() and self.loop_end_ms > 0:
            if next_time_ms >= self.loop_end_ms:
                # ループ開始点に戻る
                self.seek_to_time(self.loop_start_ms)
                return
        
        # 通常の終了チェック
        if next_frame >= self.total_frames:
            self.timer.stop()
            self.play_btn.setText("再生")
            return
        
        self.seek_to_frame(next_frame)
        self.seek_slider.setValue(next_frame)
    
    def display_frame(self, frame):
        """フレームを表示"""
        if frame is None:
            return
        
        # OpenCVのBGRからQtのRGBに変換
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # ROI表示
        if self.show_roi_check.isChecked():
            rgb_frame = self.draw_roi(rgb_frame)
        
        # 字幕オーバーレイ
        if self.show_subtitle_check.isChecked() and self.current_subtitle_text:
            rgb_frame = self.draw_subtitle_overlay(rgb_frame)
        
        # NumPy配列からQPixmapに変換
        height, width, channel = rgb_frame.shape
        bytes_per_line = 3 * width
        q_image = QPixmap.fromImage(
            QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
        )
        
        # ラベルのサイズに合わせてスケール
        scaled_pixmap = q_image.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        self.video_label.setPixmap(scaled_pixmap)
    
    def draw_roi(self, frame):
        """ROI（抽出領域）を描画"""
        height, width = frame.shape[:2]
        
        # 下段30%の領域を描画（DESIGN.mdの既定値）
        roi_top = int(height * 0.7)
        
        # 赤い枠線で描画
        cv2.rectangle(frame, (0, roi_top), (width, height), (255, 0, 0), 2)
        
        # ラベル
        cv2.putText(frame, "OCR Area", (10, roi_top - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        
        return frame
    
    def update_display(self):
        """表示の更新"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
                self.display_frame(frame)
    
    def update_time_display(self):
        """時間表示の更新"""
        current_time = self.format_time(self.current_time_ms)
        total_time = self.format_time(int(self.total_frames * 1000 / self.fps))
        self.time_label.setText(f"{current_time} / {total_time}")
    
    def format_time(self, time_ms: int) -> str:
        """時間をフォーマット（HH:MM:SS）"""
        seconds = time_ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def closeEvent(self, event):
        """ウィンドウクローズ時の処理"""
        if self.cap:
            self.cap.release()
        event.accept()
    
    def set_subtitles(self, subtitles):
        """字幕リストを設定"""
        self.current_subtitles = subtitles
        self.update_current_subtitle()
    
    def update_current_subtitle(self):
        """現在時間の字幕テキストを更新"""
        self.current_subtitle_text = ""
        
        for subtitle in self.current_subtitles:
            if subtitle.start_ms <= self.current_time_ms <= subtitle.end_ms:
                self.current_subtitle_text = subtitle.text
                break
    
    def draw_subtitle_overlay(self, frame):
        """字幕オーバーレイを描画"""
        if not self.current_subtitle_text:
            return frame
        
        height, width = frame.shape[:2]
        
        # 字幕表示位置（下部中央）
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        thickness = 2
        
        # テキストサイズを計算
        lines = self.current_subtitle_text.split('\n')
        line_height = 30
        max_width = 0
        
        for line in lines:
            (text_width, text_height), _ = cv2.getTextSize(line, font, font_scale, thickness)
            max_width = max(max_width, text_width)
        
        # 背景矩形
        bg_height = len(lines) * line_height + 20
        bg_y = height - bg_height - 20
        bg_x = (width - max_width) // 2 - 10
        
        # 半透明背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (bg_x, bg_y), (bg_x + max_width + 20, bg_y + bg_height), 
                     (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
        
        # テキスト描画
        y_offset = bg_y + 30
        for line in lines:
            (text_width, _), _ = cv2.getTextSize(line, font, font_scale, thickness)
            x_pos = (width - text_width) // 2
            
            # 白い縁取り
            cv2.putText(frame, line, (x_pos, y_offset), font, font_scale, (0, 0, 0), thickness + 2)
            # 白いテキスト
            cv2.putText(frame, line, (x_pos, y_offset), font, font_scale, (255, 255, 255), thickness)
            
            y_offset += line_height
        
        return frame
    
    def set_loop_start(self):
        """ループ開始点を現在時間に設定"""
        self.loop_start_ms = self.current_time_ms
        self.clear_loop_btn.setEnabled(True)
        self.update_loop_display()
    
    def set_loop_end(self):
        """ループ終了点を現在時間に設定"""
        self.loop_end_ms = self.current_time_ms
        if self.loop_end_ms <= self.loop_start_ms:
            self.loop_end_ms = self.loop_start_ms + 2000  # 最低2秒
        self.clear_loop_btn.setEnabled(True)
        self.update_loop_display()
    
    def set_loop_region(self, start_ms: int, end_ms: int):
        """ループ区間を設定（外部から）"""
        self.loop_start_ms = start_ms
        self.loop_end_ms = end_ms
        self.loop_check.setChecked(True)
        self.clear_loop_btn.setEnabled(True)
        self.update_loop_display()
    
    def clear_loop(self):
        """ループ設定をクリア"""
        self.loop_start_ms = 0
        self.loop_end_ms = 0
        self.loop_check.setChecked(False)
        self.clear_loop_btn.setEnabled(False)
        self.update_loop_display()
    
    def update_loop_display(self):
        """ループ表示を更新"""
        if self.loop_start_ms > 0 and self.loop_end_ms > 0:
            start_time = self.format_time(self.loop_start_ms)
            end_time = self.format_time(self.loop_end_ms)
            self.loop_check.setText(f"ループ再生 ({start_time} - {end_time})")
        else:
            self.loop_check.setText("ループ再生")