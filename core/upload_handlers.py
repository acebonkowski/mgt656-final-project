"""Bounded, memory-only uploads: never fall back to temporary disk files."""
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload

from core.photo_storage import MAX_PHOTO_BYTES


class ProfilePhotoUploadHandler(FileUploadHandler):
    def __init__(self, request=None):
        super().__init__(request)
        self.total = 0
        self.count = 0

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.count += 1
        if self.count > 1:
            self.request.photo_upload_error = "Upload one photo at a time."
            raise StopUpload(connection_reset=False)
        self.buffer = BytesIO()

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > MAX_PHOTO_BYTES:
            self.request.photo_upload_error = "Choose a photo no larger than 5 MB."
            raise StopUpload(connection_reset=False)
        self.buffer.write(raw_data)
        return None

    def file_complete(self, file_size):
        self.buffer.seek(0)
        return InMemoryUploadedFile(self.buffer, self.field_name, self.file_name,
                                   self.content_type, file_size, self.charset)
