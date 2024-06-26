# This code was adapted from https://github.com/ClarityCoders/GoogleDrive
# His youtube video for reference https://www.youtube.com/watch?v=LSP9PUx7n04

# This adaptation includes:
# - Synchronization:
#   - Downloads and uploads files when needed to make local and remote origins identical
#   - Checks for file modification and updates origin with the oldest file
# - Clean logging to stdout and to file (if specified in configuration)

import pickle
import json
import os
import io
import hashlib


from loguru import logger
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from apiclient.http import MediaFileUpload, MediaIoBaseDownload


import time
import re
import calendar
from datetime import datetime

import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--local-folder", type=str, default=os.path.realpath("."))
parser.add_argument("--drive-folder-id", type=str, required=True)
parser.add_argument("--download-only", type=str, default=True)
parser.add_argument("--credentials", type=str, default="client_secrets.json")
parser.add_argument("--token-cache", type=str, default="token.pickle")


class Utils:
    # Return list of all files in specified backup folder
    @classmethod
    def list_local_files(cls, local_path):
        return os.listdir(local_path)

    # Get last modification timestamp from local file
    @classmethod
    def get_local_file_timestamp(cls, path):
        unix_timestamp = os.path.getmtime(path)
        utc_datetime = cls.convert_timestamp_datetime(unix_timestamp)
        utc_timestamp = cls.convert_datetime_timestamp(utc_datetime)

        return int(unix_timestamp)

    # Convert Google Drive's datetime to local timestamp
    @classmethod
    def convert_datetime_timestamp(cls, date):
        date = re.sub(r"\.\d+", "", date)
        time_object = time.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
        timestamp = calendar.timegm(time_object)

        return int(timestamp)

    # Convert local timestamp to Google Drive's datetime
    @classmethod
    def convert_timestamp_datetime(cls, timestamp):
        datetime_object = datetime.utcfromtimestamp(timestamp)

        return datetime_object.isoformat("T") + "Z"


API_URL = ["https://www.googleapis.com/auth/drive"]


class Drive:

    def __init__(self, token_fname):
        creds = None
        self.token_fname = token_fname

        # Checks if authentication token exists, then load it
        if os.path.exists(self.token_fname):
            with open(self.token_fname, "rb") as token:
                creds = pickle.load(token)

        # Create new authencation token if it does not exist or has expired
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    ARGS.credentials, API_URL
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_fname, "wb") as token:
                pickle.dump(creds, token)

        self.__service = build("drive", "v3", credentials=creds)

    # List all files inside specified Drive folder
    def list_files(self, folder_id):
        # Call API
        response = (
            self.__service.files()
            .list(
                q=f"'{folder_id}' in parents",
                fields="files(id,name,modifiedTime,mimeType,md5Checksum)",
            )
            .execute()
        )

        # Return all file names
        files_dict = {"all": response.get("files", []), "names": []}
        for item in files_dict["all"]:
            files_dict["names"].append(item["name"])

        return files_dict

    # Download file from drive to local folder
    def download_file(self, filename, local_path, file_id, update=False):
        local_absolute_path = f"{local_path}/{filename}"

        # Request for download API
        request = self.__service.files().get_media(fileId=file_id)

        # File stream
        fh = io.BytesIO()

        # Setup request and file stream
        downloader = MediaIoBaseDownload(fh, request)

        # Wait while file is being downloaded
        done = False
        while done is False:
            done = downloader.next_chunk()

        # Save download buffer to file
        with open(local_absolute_path, "wb") as out:
            out.write(fh.getbuffer())

        # Change local modification time to match remote
        modified_time = (
            self.__service.files()
            .get(fileId=file_id, fields="modifiedTime")
            .execute()["modifiedTime"]
        )
        modified_timestamp = Utils.convert_datetime_timestamp(modified_time)
        os.utime(local_absolute_path, (modified_timestamp, modified_timestamp))

        if update is not False:
            logger.info(
                "Local file '{}' updated successfully in folder '{}'.",
                filename,
                local_absolute_path,
            )
        else:
            logger.info(
                "File '{}' downloaded successfully in folder '{}'.",
                filename,
                local_absolute_path,
            )

    # Upload file from local to drive folder
    def upload_file(self, filename, local_path, folder_id, update=False):
        if ARGS.download_only:
            return False

        local_absolute_path = f"{local_path}/{filename}"

        # Custom file metadata for upload (modification time matches local)
        modified_timestamp = Utils.get_local_file_timestamp(local_absolute_path)
        file_metadata = {
            "name": filename,
            "modifiedTime": Utils.convert_timestamp_datetime(modified_timestamp),
            "parents": [folder_id],
        }

        # File definitions for upload
        media = MediaFileUpload(local_absolute_path)

        # Send POST request for upload API
        try:
            if update != False:
                uploaded_file = (
                    self.__service.files()
                    .update(fileId=update, media_body=media)
                    .execute()
                )

                logger.info(
                    "Remote file '{}' updated successfully in folder '{}'.",
                    filename,
                    local_absolute_path,
                )

            else:
                uploaded_file = (
                    self.__service.files()
                    .create(body=file_metadata, media_body=media, fields="id")
                    .execute()
                )

                logger.info(
                    "File '{}' uploaded successfully in folder '{}'.",
                    filename,
                    local_absolute_path,
                )

            return uploaded_file
        except:
            logger.error("Error uploading file: {}.", filename)

            return False

    # Create folder with respective parent Folder ID
    def upload_folder(self, foldername, folder_id):
        if ARGS.download_only:
            return False

        # Custom folder metadata for upload
        folder_metadata = {
            "name": foldername,
            "parents": [folder_id],
            "mimeType": "application/vnd.google-apps.folder",
        }

        try:
            # Send POST request for upload API
            uploaded_folder = (
                self.__service.files().create(body=folder_metadata).execute()
            )
            logger.info("Remote folder created: '{}'.", uploaded_folder["name"])

            return uploaded_folder["id"]
        except:
            logger.error("Error creating folder: '{}'.", folder_metadata["name"])

            return False

    # Verifies if file was modified or not
    def compare_files(self, local_file_data, remote_file_data):
        modified = False

        if local_file_data["modifiedTime"] > remote_file_data["modifiedTime"]:
            modified = "local"
        elif local_file_data["modifiedTime"] < remote_file_data["modifiedTime"]:
            modified = "remote"

        remote_md5 = remote_file_data.get("md5Checksum", None)
        if modified and remote_md5:
            # check md5
            with open(local_file_data["path"], "rb") as f:
                # read contents of the file
                local_md5 = hashlib.md5(f.read()).hexdigest()
            if remote_md5 == local_md5:
                modified = False
            # else:
            #     print("Do something here")
            #     risen

        return modified

    # Recursive method to synchronize all folder and files
    def synchronize(self, local_path, folder_id, recursive=False):
        logger.trace(
            "{} folder '{}'",
            "Recursively synchronizing" if recursive else "Synchronizing",
            local_path,
        )

        # Check if local path exists, if not, creates folder
        if not os.path.exists(local_path):
            os.makedirs(local_path)

        # List remote and local files
        drive_files = self.list_files(folder_id)
        local_files = Utils.list_local_files(local_path)

        # Compare files with same name in both origins and check which is newer, updating
        same_files = list(set(drive_files["names"]) & set(local_files))

        if len(same_files) == 0 and not recursive:
            logger.info("No files to update on folder '{}'.", local_path)

        for sm_file in same_files:
            local_absolute_path = f"{local_path}/{sm_file}"

            remote_file_data = next(
                item for item in drive_files["all"] if item["name"] == sm_file
            )  # Filter to respective file
            remote_file_data["modifiedTime"] = Utils.convert_datetime_timestamp(
                remote_file_data["modifiedTime"]
            )

            local_file_data = dict(path=local_absolute_path)
            local_file_data["name"] = sm_file
            try:
                local_file_data["modifiedTime"] = Utils.get_local_file_timestamp(
                    local_absolute_path
                )

                # Checks if files were modified on any origin
                modified = self.compare_files(local_file_data, remote_file_data)
            except FileNotFoundError:
                modified = "remote"
                # force it to download it

            if modified == "local":
                continue
                if os.path.isdir(local_absolute_path):
                    self.synchronize(
                        local_absolute_path, remote_file_data["id"], recursive=True
                    )
                else:
                    self.upload_file(
                        sm_file, local_path, folder_id, remote_file_data["id"]
                    )

            elif modified == "remote":
                if remote_file_data["mimeType"] == "application/vnd.google-apps.folder":
                    self.synchronize(
                        local_absolute_path, remote_file_data["id"], recursive=True
                    )
                else:
                    self.download_file(
                        sm_file, local_path, remote_file_data["id"], True
                    )

        # Compare different files in both origins and download/upload what is needed
        different_files = list(set(drive_files["names"]) ^ set(local_files))

        if len(different_files) == 0 and not recursive:
            logger.info("No files to download/upload on folder '{}'.", local_path)

        for diff_file in different_files:
            # If file is only on Google Drive (DOWNLOAD)
            if diff_file in drive_files["names"]:
                for remote_file in drive_files["all"]:
                    if remote_file["name"] == diff_file:
                        if (
                            remote_file["mimeType"]
                            == "application/vnd.google-apps.folder"
                        ):
                            local_absolute_path = f"{local_path}/{diff_file}"
                            self.synchronize(
                                local_absolute_path, remote_file["id"], recursive=True
                            )  # Recursive to download files inside folders
                        else:
                            self.download_file(
                                remote_file["name"], local_path, remote_file["id"]
                            )

            # IF file is only on local (UPLOAD)
            else:
                local_absolute_path = f"{local_path}/{diff_file}"

                # Check if path redirects to a file or folder
                if os.path.isdir(local_absolute_path):
                    created_folder_id = self.upload_folder(diff_file, folder_id)
                    if created_folder_id != False:
                        self.synchronize(
                            local_absolute_path, created_folder_id, recursive=True
                        )  # Recursive to upload files inside folders
                else:
                    self.upload_file(diff_file, local_path, folder_id)


ARGS = None


def run():
    global ARGS
    ARGS = parser.parse_args()

    logger.success("Starting synchronization...")

    # Instantiate Drive class and synchronize files
    my_drive = Drive(ARGS.token_cache)
    my_drive.synchronize(ARGS.local_folder, ARGS.drive_folder_id)

    logger.success("Synchronization finalized!")


if __name__ == "__main__":
    run()
