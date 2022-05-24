import os
import subprocess
import sys
dir_path = os.path.dirname(os.path.realpath(__file__))

subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", dir_path+'/req.txt'])

import qbittorrentapi
import json
import requests
from time import sleep
import socket
import platform
import ftplib

class FtpUploadTracker:
    sizeWritten = 0
    totalSize = 0
    lastShownPercent = 0
    
    def __init__(self, totalSize):
        self.totalSize = totalSize
    
    def handle(self, block):
        self.sizeWritten += 1024
        percentComplete = round((self.sizeWritten / self.totalSize) *100)
        
        if (self.lastShownPercent != percentComplete):
            self.lastShownPercent = percentComplete
            print(f"Uploading: {percentComplete}%")

class main():
    plexRequestAmount = 0
    sizeWritten = 0
    downloadedMedia = []
    searchedMedia = []
    plexFolders = ['Movies', 'Shows']
    torrentClientOpen = False

    def createMagnetURL(torrentList, torrentURL):
        for i in torrentList:
            if (i["quality"] == "2160p" or i["quality"] == "1080p" or i["quality"] == "720p"):
                print(f"Found {i['quality']} Torrent")
                hash = str(i["hash"])
        magnetUrl = f'magnet:?xt=urn:btih:{hash}&dn={torrentURL}&tr=http://track.one:1234/announce&tr=udp://track.two:80'
        return magnetUrl

    def getPlexRequests():
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
            }
            r = requests.post('https://www.quackyos.com/QuackyForum/scripts/getPlexRequestsAuto.php', headers=headers, timeout=10)
            jsonResponse = r.json()
            for x in jsonResponse:
                # Get Only The Year From Media Release Date

                if (main.plexRequestAmount != len(jsonResponse)):
                    try:
                        formatedYear = ' ' + str(x['mediaReleaseDate']).split('-')[0]
                    except:
                        print("No Year Found")
                    
                    main.checkPirateDB(x['mediaType']+'s', str(x['id']), str(x['mediaName']), str(formatedYear))
                    main.plexRequestAmount+=1
                
        except (requests.ReadTimeout, requests.ConnectionError):
            main.plexRequestAmount=0
            print("Plex Request Timeout")

    def changePlexRequestStatus(mediaId, status):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
        }
        pload= {'username':'QUACKYOS_USERNAME', 'password':'QUACKYOS_PASSWORD', 'id':mediaId,'status':status}
        r = requests.post('https://www.quackyos.com/QuackyForum/scripts/changeStatus.php', data=pload, headers=headers, timeout=10)
        print(r.text)

    def deleteAndNotifyPlexRequest(mediaId):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
        }
        pload= {'username':'QUACKYOS_USERNAME', 'password':'QUACKYOS_PASSWORD', 'deleteId':mediaId}
        r = requests.post('https://www.quackyos.com/QuackyForum/scripts/deleteAndNotify.php', data=pload, headers=headers, timeout=30)
        print(r.text)

    def uploadMedia(fileLocation, mediaId, status):
        ftp = ftplib.FTP("FTP IP")
        ftp.login("FTP USERNAME", "FTP PASSWORD")

        mediaType = fileLocation
        if ('Movies' in mediaType):
            mediaType = 'Movies'
        else:
            mediaType = 'Shows'

        ftp.cwd(f'/PLEX/{mediaType}')

        tester = ['.mp4','.mkv','.m4v','.avi','.flv','.mov','.amv']

        for x in tester:
            for searchFile in os.listdir(fileLocation):
                if searchFile.endswith(x):
                    try:
                        print(f"Location: {fileLocation}")
                        totalSize = os.path.getsize(f'{fileLocation}/{searchFile}')
                        print('Total Size: ' + str(totalSize))
                        print(f"Starting Upload: {searchFile}")
                        removeChars = str(f'{searchFile}').replace(']', '').replace('[','')
                        os.rename(f'{fileLocation}/{searchFile}', f'{fileLocation}/{removeChars}')
                        # Change Plex Request
                        main.changePlexRequestStatus(mediaId, status)
                        searchFile = removeChars
                        # FTP upload
                        file = open(f'{fileLocation}/{searchFile}','rb')
                        uploadTracker = FtpUploadTracker(int(totalSize))
                        if (ftp.storbinary(f'STOR {searchFile}', file, 1024, uploadTracker.handle)):
                            print(f"Uploaded {searchFile}")
                            main.deleteAndNotifyPlexRequest(mediaId)
                    except Exception as e:
                        print("File Type Not Found: " + str(e))

    def openMagnetURL(magnetURL):
        machineOs = platform.system()
        if (machineOs == 'Darwin' or machineOs == 'Linux'):
            subprocess.call(['open', magnetURL])
        else:
            os.startfile(magnetURL)

    def write_json(new_data, key, filename):
        with open(filename,'r+') as file:
            # First we load existing data into a dict.
            file_data = json.load(file)
            # Join new_data with file_data inside emp_details
            file_data[key].append({'title':new_data})
            # Sets file's current position at offset.
            file.seek(0)
            # convert back to json.
            json.dump(file_data, file, indent = 4)

    def checkPirateDB(mediaType, mediaId, mediaName, year):
        # Vars
        relatedMedia = []

        if (main.checkVPN() and mediaName not in main.searchedMedia):
            try:
                # Check Movie DB
                if (mediaType == 'Movies'):
                    print(f"Searching Movie DB: {mediaName} {year}")

                    headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
                    }
                    r = requests.post('https://yts.torrentbay.to/api/v2/list_movies.json?query_term=' + mediaName + year, headers=headers, timeout=10)
                    jsonResponse = r.json()
                    jsonResponse = jsonResponse["data"]["movies"]

                    for x in jsonResponse:
                        relatedMedia.append(x['title'])
                        if (mediaName.lower() == x['title'].lower() or mediaName.lower() == x['title_long'].lower() and mediaName not in main.downloadedMedia):
                            url = x['url']
                            torrents = x['torrents']
            
                            # Open Magnet URL
                            main.torrentClient('add', main.createMagnetURL(torrents,url), 'Movies', mediaName, mediaId)
                            print("DOWNLOADING: " + str(x['title']))

                            main.downloadedMedia.append(mediaName)

                            # Change Request status
                            main.changePlexRequestStatus(mediaId, 'Downloading')
                            break
                    else:
                        print('Couldnt Find Exact Match!, heres a list of related media.')
                        print(relatedMedia)
                elif (mediaType == 'Shows'):
                    print(f'Searching Show DB: {mediaName} {year}')

                # Add media to searched
                main.searchedMedia.append(mediaName)
                
                print(f'Searched: {mediaName} {year}')
                
                
            except (KeyError, requests.ReadTimeout, requests.ConnectionError) as e:
                if (e == KeyError):
                    print('Couldnt find ' + mediaName)
                elif (e == requests.ReadTimeout):
                    main.plexRequestAmount=0
                    print('DB Request Timeout')
                    

    def torrentClient(request, url, mediaType, mediaName, mediaId):
        # instantiate a Client using the appropriate WebUI configuration
        qbt_client = qbittorrentapi.Client(
            host='localhost',
            port=8080,
            username='admin',
            password='adminadmin',
        )

        # the Client will automatically acquire/maintain a logged-in state
        # in line with any request. therefore, this is not strictly necessary; 
        # however, you may want to test the provided login credentials.
        try:
            qbt_client.auth_log_in()
        except qbittorrentapi.LoginFailed as e:
            print(e)

        if request == 'add':
            qbt_client.torrents_add(urls=url,save_path=f"{dir_path}/upload/{mediaType}/", rename=f"{mediaName}*{mediaId}")

        for torrent in qbt_client.torrents_info():
            if (torrent.state == 'pausedDL'):
                print(f'Resuming: {torrent.name}')
                qbt_client.torrents.resume(torrent.hash)

            elif (torrent.state == 'stalledUP' or torrent.state=='uploading'):
                torrentId = str(torrent.name).split('*')
                try:
                    print(torrentId[1])
                except:
                    print('No Torrent Id')
                # pause all torrents
                print('Pausing Torrents...')
                qbt_client.torrents.pause.all()
                sleep(5)
                print('Disconnecting VPN...')
                main.windscribe(['disconnect'])
                sleep(5)
                main.uploadMedia(torrent.content_path, torrentId, 'Uploading')
    def openTorrentClient():
        if (main.torrentClientOpen == False):
            print('Opening Torrent Client...')
            subprocess.Popen(["C:\Program Files\qBittorrent\\qbittorrent.exe"])
            main.torrentClientOpen = True
            sleep(5)
                

    def readConfig(path, key, item):
        output = []
        # Open JSON file
        f = open(dir_path+path)
        data = json.load(f)
        
        if key == '':
            return data
        elif item == '':
            return data[key]
        else:
            for i in data[key]:
                output.append(i[item])
            return str(output)

    def windscribe(arguments):
        subprocess.check_call([r"C:\Program Files (x86)\Windscribe\windscribe-cli.exe"] + arguments)
    
    def checkVPN():
        try:
            getIP = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            getIP.connect(("8.8.8.8", 80))
            currentIP = str([getIP.getsockname()[0]])

            if (currentIP == str(main.readConfig('/config.json','default', 'ip'))):
                return False
            else:
                return True
        except (OSError,KeyboardInterrupt) as e:
            if e.errno == 51:
                main.plexRequestAmount=0
                print('Network Unreachable')

while True:
    sleep(1)
    try:
        if (main.checkVPN()):
            main.openTorrentClient()
            main.getPlexRequests()
            main.torrentClient('','','','','')
        else:
            main.plexRequestAmount=0
            print('VPN OFF, Turning On Now...')
            main.windscribe(['connect', 'Los Angeles'])
            sleep(5)
            main.openTorrentClient()
    except Exception as e:
        print(e)