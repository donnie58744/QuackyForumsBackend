import os
import subprocess
import sys

dir_path = os.path.dirname(os.path.realpath(__file__))

subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", dir_path+'/req.txt'])

import qbittorrentapi
import rarbgapi
import json
import re
import requests
from requests.adapters import HTTPAdapter, Retry
from datetime import datetime,timedelta,date
from time import sleep
import platform
import ftplib

class FtpUploadTracker:
    sizeWritten = 0
    totalSize = 0
    lastShownPercent = 0
    fileTypes = ['.mkv','.flv','.avi','.mp4','.m4v']
    
    def __init__(self, totalSize, mediaId, searchFile, fileExtension):
        self.totalSize = totalSize
        self.searchFile = searchFile
        self.mediaId = mediaId
        self.fileExtension = fileExtension
    
    def handle(self, block):
        self.sizeWritten += 8192
        percentComplete = round((self.sizeWritten / self.totalSize) *100)
        
        if (self.lastShownPercent != percentComplete):
            self.lastShownPercent = percentComplete
            if (self.fileExtension in self.fileTypes):
                main.changePlexRequestStatus('https://www.quackyos.com/QuackyForumDev/scripts/changeDownloadProgress.php', self.mediaId, percentComplete)
            print(f"Uploading: {percentComplete}%")
            main.uploading = True
            if (percentComplete >= 100):
                print(f"Uploaded {self.searchFile}")
                


class CheckShowDB():
    client = rarbgapi.RarbgAPI()
    queued = []
    timeoutCounter = 0


    def checkIt(mediaId, imdb_ID, mediaName, seasonNum, timedOut=None):
        seasonNum = str(seasonNum).strip('[').strip(']').replace('"', '').split(',')

        print('s' + str(seasonNum))
        print(mediaName)

        for index, i in enumerate(seasonNum, start=1):
            torrents = [[],[],[]]
            if (CheckShowDB.timeoutCounter >= 30):
                print('Show DB Error Skipping...')
                CheckShowDB.timeoutCounter = 0
                break
            else:
                try:
                    print('Searching....' + str(imdb_ID) + ' ' + str(i))
                    for torrent in CheckShowDB.client.search(search_imdb=f'{imdb_ID}', categories=[rarbgapi.RarbgAPI.CATEGORY_TV_EPISODES, rarbgapi.RarbgAPI.CATEGORY_TV_EPISODES_HD, rarbgapi.RarbgAPI.CATEGORY_TV_EPISODES_UHD], extended_response=True, limit=100):
                        if (re.search(r'\b'+i+r'\b', str(torrent))):
                            torrents[0].append(mediaName)
                            torrents[1].append(torrent.seeders)
                            torrents[2].append(torrent.download)
                            print(str(torrent) + str(torrent.seeders))
                    print(torrents[1])
                    highestSeeder = torrents[1].index(max(torrents[1]))
                    highestSeederName = torrents[0][highestSeeder]
                    highestSeederURL = torrents[2][highestSeeder]
                    CheckShowDB.queued.append(str(highestSeederURL))
                    print(highestSeederURL)
                    main.torrentClient('add', highestSeederURL, 'Shows', mediaName, i,mediaId)
                    timedOut = False

                except ValueError as e:
                    print(e)
                    print(i)
                    CheckShowDB.timeoutCounter += 1
                    CheckShowDB.checkIt(mediaId, imdb_ID, mediaName, i, True)
                except KeyboardInterrupt:
                    exit()
                except:
                    print(sys.exc_info()[0])
                

class main():
    plexTimer = 0
    plexTimeout = 15
    downloadedMedia = []
    torrentClientOpen = False
    uploading = False
    torrentTimeoutCounter = 0
    lastDownloadProgress = 0
    stalledTorrents = []

    FTPip = ""
    FTPusername = ""
    FTPPassword = ""
    quackyosUsername = ""
    quackyosPassword = ""

    def createMagnetURL(torrentList, torrentURL):
        for i in torrentList:
            if (i["quality"] == "1080p" or i["quality"] == "720p"):
                print(f"Found {i['quality']} Torrent")
                hash = str(i["hash"])
        magnetUrl = f'magnet:?xt=urn:btih:{hash}&dn={torrentURL}&tr=http://track.one:1234/announce&tr=udp://track.two:80'
        return magnetUrl

    def getPlexRequests():
        try:
            if (main.plexTimer >= main.plexTimeout or main.plexTimer == 0):
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
                }
                r = requests.post('https://www.quackyos.com/QuackyForumDev/scripts/getPlexRequestsAuto.php', headers=headers, timeout=10)
                jsonResponse = r.json()
                for x in jsonResponse:
                    main.checkPirateDB(x['mediaType']+'s', str(x['id']), str(x['mediaName']), x['seasons'], str(x['mediaReleaseDate']), str(x['mediaRelease']), str(x['imdbID']))
                main.plexTimer = 0
            main.plexTimer+=1
                
        except (requests.ReadTimeout, requests.ConnectionError):
            main.plexTimer=0
            print("Plex Request Timeout")

    def changePlexRequestStatus(url, mediaId, status, release=None, date=None):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
            }
            pload= {'username':main.quackyosUsername, 'password':main.quackyosPassword, 'id':mediaId, 'release':release, 'status':status, 'date':date}
            s = requests.Session()
            retries = Retry(total=5,
                            backoff_factor=0.1,
                            status_forcelist=[ 500, 502, 503, 504 ])
            s.mount('https://', HTTPAdapter(max_retries=retries))
            s.post(url, data=pload, headers=headers, timeout=30)
        except Exception as e:
            print(e)
            pass

    def deleteAndNotifyPlexRequest(mediaId):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
        }
        pload= {'username':main.quackyosUsername, 'password':main.quackyosPassword, 'deleteId':mediaId}
        r = requests.post('https://www.quackyos.com/QuackyForumDev/scripts/deleteAndNotify.php', data=pload, headers=headers, timeout=30)
        print(r.text)
    
    def seasonList(mediaId, data,request,lock):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
        }
        pload= {'username':main.quackyosUsername, 'password':main.quackyosPassword, 'mediaId':mediaId, 'data':data,'request':request, 'lock':lock}
        r = requests.post('https://www.quackyos.com/QuackyForumDev/scripts/seasonList.php', data=pload, headers=headers, timeout=30)
        print(r.text)

    def uploadMedia(fileLocation, mediaName, torrentSeason,mediaId, status, folderUpload=None, folderPath=None):
        ftp = ftplib.FTP(main.FTPip, main.FTPusername, main.FTPPassword)
        main.uploading = True
        mediaType = fileLocation

        if ('Movies' in mediaType):
            mediaType = 'Movies'
            torrentSeason = ''
        else:
            mediaType = 'Shows'
            try:
                # Create Main Show Folder
                ftp.mkd(f'/PLEX/{mediaType}/{mediaName}/')
                ftp.cwd(f'/PLEX/{mediaType}/{mediaName}/')
            except Exception as e:
                print('Main Folder Already Exsist')
                pass

        os.chdir(fileLocation)

        # Create Main Media Folder only once
        mediaName = str(mediaName).replace(':', '')
        if (not folderUpload):
            if (mediaType == 'Movie'):
                # Create and Enter Main Movie Folder
                ftp.mkd(f'/PLEX/{mediaType}/{mediaName}/')
                ftp.cwd(f'/PLEX/{mediaType}/{mediaName}/')
            else:
                # Create and Enter Main Season Folder
                try:
                    ftp.mkd(f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}')
                    ftp.cwd(f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}')
                except Exception as e:
                    print('Dont Worry! ' + str(e))
                    pass
            folderPath = ''

        for searchFile in os.listdir(fileLocation):
            print(f"Location: {fileLocation}")
            totalSize = os.path.getsize(f'{fileLocation}/{searchFile}')
            print('Total Size: ' + str(totalSize))
            print(f"Starting Upload: {searchFile}")
            # FTP upload
            # Read file in binary mode
            sleep(5)
            # Change Plex Request
            main.changePlexRequestStatus('https://www.quackyos.com/QuackyForumDev/scripts/changeDownloadProgress.php', mediaId, 0)
            main.changePlexRequestStatus('https://www.quackyos.com/QuackyForumDev/scripts/changeStatus.php', mediaId, status)
            if os.path.isfile(fileLocation + r'\{}'.format(searchFile)):
                print('file')
                fh = open(searchFile, 'rb')
                filename, file_extension = os.path.splitext(f'{fileLocation}/{searchFile}')
                uploadTracker = FtpUploadTracker(int(totalSize), mediaId, searchFile, file_extension)
                print('Server Location: ' + f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}/{folderPath}/')
                ftp.cwd(f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}/{folderPath}/')
                ftp.storbinary('STOR %s' % searchFile, fh, 8192, uploadTracker.handle)
                fh.close()
            elif os.path.isdir(fileLocation + r'\{}'.format(searchFile)):
                try:
                    print('folder'+folderPath)
                    if (folderPath):
                        print(f'1 /PLEX/{mediaType}/{mediaName}/{torrentSeason}/{folderPath}/{searchFile}')
                        ftp.mkd(f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}/{folderPath}/{searchFile}')
                    else:
                        print('2')
                        ftp.mkd(f'{searchFile}')
                    print('Server Location: ' + f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}/{folderPath}/{searchFile}/')
                    ftp.cwd(f'/PLEX/{mediaType}/{mediaName}/{torrentSeason}/{folderPath}/{searchFile}/')
                    main.uploadMedia(fileLocation + r'\{}'.format(searchFile), mediaName, torrentSeason, mediaId, status, True, f'{folderPath}/{searchFile}')
                    os.chdir(fileLocation)
                except Exception as e:
                    print(e)
                    pass

    def downloadTorrent(get, mediaId, mediaType, mediaName, seasons):
        url = get['url']
        torrents = get['torrents']

        # Open Magnet URL
        main.torrentClient('add', main.createMagnetURL(torrents,url), mediaType, mediaName, seasons,mediaId)
        print("DOWNLOADING: " + str(get['title']))

    def checkPirateDB(mediaType, mediaId, mediaName, seasons,releaseDate, mediaRelease, movieDB_ID):
        # Vars
        relatedMedia = []
        try:
            print('Downloaded Media' + str(main.downloadedMedia))
            if (mediaRelease == 'Released' and mediaName not in main.downloadedMedia and movieDB_ID != ''):
                # Check Movie DB
                if (mediaType == 'Movies'):
                    print(f"Searching Movie DB: {mediaName} {releaseDate}")
                    
                    headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.12; rv:55.0) Gecko/20100101 Firefox/55.0',
                    }
                    r = requests.get('https://yts.mx/api/v2/list_movies.json?query_term=' + movieDB_ID, headers=headers, timeout=30)
                    if (str(r) == '<Response [403]>'):
                        print('Error Searching...' + f' {mediaName} {str(movieDB_ID)}')
                    else:
                        jsonResponse = r.json()
                        jsonResponse = jsonResponse["data"]["movies"]

                        for x in jsonResponse:
                            if (x['imdb_code'] == movieDB_ID):
                                main.downloadTorrent(x, mediaId, mediaType, mediaName, seasons)
                                break
                            else:
                                relatedMedia.append(x['title'])
                        else:
                            print('Couldnt Find Exact Match!, heres a list of related media.')
                            print(relatedMedia)
                            
                elif (mediaType == 'Shows'):
                    print(f'Searching Show DB: {mediaName} {releaseDate}')
                    
                    CheckShowDB.checkIt(mediaId, movieDB_ID, mediaName, seasons)
                
                print(f'Searched: {mediaName} {releaseDate}')
            else:
                print(f'Skipped {mediaName} {releaseDate}')

        #Cant Find Movie In DB
        except KeyError as e:
            print(f'Couldnt find {mediaName} Chaning Media Release Date...')
            # Add 45 Days to release date
            date_time_str = str(releaseDate)
            date_time_obj = datetime.strptime(date_time_str, '%Y-%m-%d')
            newDate = date_time_obj.date() + timedelta(days=45)
            main.changePlexRequestStatus('https://www.quackyos.com/QuackyForumDev/scripts/changeReleaseDate.php', mediaId, 'Queued', 'Not Released', newDate)

        except  requests.ReadTimeout as e:
            main.plexRequestAmount=0
            print('DB Request Timeout')
        except requests.ConnectionError as e:
            main.plexRequestAmount=0
            print('DB Request Timeout')
                    
    def torrentClient(request=None, url=None, mediaType=None, mediaName=None, seasons=None, mediaId=None):
        try:
            if request == 'open':
                if (main.torrentClientOpen == False):
                    print('Opening Torrent Client...')
                    subprocess.Popen(["C:\Program Files\qBittorrent\qbittorrent.exe"])
                    main.torrentClientOpen = True
                else:
                    print('Torrent Client Already Opended')
            stalledTimeout = 120
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
                pass

            if (request == 'add'):
                qbt_client.torrents_add(urls=url,save_path=f"{dir_path}/upload/{mediaType}/", rename=f"{mediaName}*{seasons}*{mediaId}*{mediaType}")
                main.changePlexRequestStatus('https://www.quackyos.com/QuackyForumDev/scripts/changeStatus.php', mediaId, 'Downloading')
                if (mediaName not in main.downloadedMedia):
                    main.downloadedMedia.append(mediaName)
            elif (request == 'close'):
                print('Shutting Down Torrent Client')
                main.torrentClientOpen = False
                qbt_client.app_shutdown()

            elif (request == 'search'):
                for torrent in qbt_client.torrents_info():
                    
                    # Resume Torrent If Paused
                    if (torrent.state == 'pausedDL'):
                        if (main.checkVPN(main.uploading)):
                            print(f'Resuming: {torrent.name}')
                            sleep(5)
                            qbt_client.torrents.resume(torrent.hash)
                    
                    # Restart Torrent Client On Stalled For x Seconds
                    elif (torrent.state == 'metaDL' or torrent.state == 'stalledDL'):
                        sleep(1)
                        if (torrent.hash not in main.stalledTorrents):
                            main.stalledTorrents.append(torrent.hash)
                        print(main.stalledTorrents)
                        main.torrentTimeoutCounter += 1
                        print (main.torrentTimeoutCounter)
                        if (main.torrentTimeoutCounter >= stalledTimeout):
                            main.torrentTimeoutCounter = 0
                            print('Restarting Client Due To Stalled Torrent')
                            main.torrentClient(request='close')
                            sleep(5)
                            main.windscribe(['disconnect'])
                        elif (main.torrentTimeoutCounter == stalledTimeout/2):
                            qbt_client.torrents.pause(main.stalledTorrents)

                    # Upload Media
                    elif (torrent.state == 'stalledUP' or torrent.state=='uploading'):
                        torrentData = str(torrent.name).split('*')
                        torrentId = torrentData[2]
                        torrentName = torrentData[0]
                        torrentSeason = torrentData[1]
                        torrentType = torrentData[3]
                        try:
                            print(torrentName)
                            print(torrentSeason)
                            print(torrentId)
                        except:
                            print('No Torrent Id')
                        # pause all torrents
                        main.uploading = True
                        print('Pausing Torrents...')
                        qbt_client.torrents.pause.all()
                        sleep(5)
                        main.torrentClient(request='close')
                        sleep(5)
                        main.windscribe(['disconnect'])
                        sleep(5)
                        main.uploadMedia(torrent.content_path, torrentName, torrentSeason, torrentId, 'Uploading')

                        # Torrent Finished Uploading, Delete Request and what not
                        main.torrentClientOpen = False
                        main.deleteAndNotifyPlexRequest(torrentId)
                        main.uploading = False

                        # Remove season from DB then check to see if seasons is empty and if so then delete

                        if (mediaType == 'Show'):
                            main.seasonList(mediaId,'update')


                    # Check if torrent is downloading and if it was stalled before
                    if (torrent.state == 'downloading' and torrent.hash in main.stalledTorrents):
                        main.stalledTorrents.remove(torrent.hash)
                        main.torrentTimeoutCounter = 0
                        print('Torrent Not Stalled No Mo!')

                    # Send Download Percent
                    if (torrent.state == 'downloading'):
                        torrentData = str(torrent.name).split('*')
                        torrentId = torrentData[2]
                        torrentName = torrentData[0]
                        torrentSeason = torrentData[1]
                        torrentType = torrentData[3]
                        downloadProgress = round(torrent.progress *100)

                        if (main.lastDownloadProgress != downloadProgress):
                            main.lastDownloadProgress = downloadProgress
                            # Change Request status
                            main.changePlexRequestStatus('https://www.quackyos.com/QuackyForumDev/scripts/changeDownloadProgress.php', torrentId, downloadProgress)
                main.clearTableLock = True
        except qbittorrentapi.APIConnectionError:
            main.plexTimer=0
            main.torrentClientOpen = False
            main.torrentClient(request='open')

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
            return output

    def windscribe(arguments):
        subprocess.check_call([r"C:\Program Files (x86)\Windscribe\windscribe-cli.exe"] + arguments)
    
    def checkVPN(uploading):
        try:
            currentIP = requests.get('https://api.ipify.org').content.decode('utf8')
            getIP = str(main.readConfig('/config.json','default', 'ip')[0])

            if (getIP == 'YOUR_IP'):
                print('Please edit the config.json file and enter in your machines IP, Hint: run ipconfig')
                exit()
            if (uploading == False):
                if (currentIP == getIP):
                    main.plexRequestAmount=0
                    print('VPN OFF, Turning On Now...')
                    main.windscribe(['connect', 'Los Angeles'])
                    sleep(30)
                else:
                    return True
            else:
                return True
        except (OSError,KeyboardInterrupt) as e:
            if e.errno == 51:
                main.plexRequestAmount=0
                print('Network Unreachable')

while True:
    sleep(1)
    if (main.checkVPN(main.uploading)):
        main.torrentClient(request='search')
        main.getPlexRequests()