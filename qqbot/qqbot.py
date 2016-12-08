#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
QQBot   -- A conversation robot base on Tencent's SmartQQ
Website -- https://github.com/pandolia/qqbot/
Author  -- pandolia@yeah.net
"""

QQBotVersion = 'v1.9.0'

import os, sys, random, pickle, time, requests, threading, Queue

from utf8logger import setLogLevel, CRITICAL, ERROR, WARN, INFO, DEBUG
from utils import jsonLoads, jsonDumps
from qqbotconf import Conf
from qrcodemanager import QrcodeManager

def main():
    if '-d' in sys.argv or '--debug' in sys.argv:
        setLogLevel('DEBUG')
    else:
        setLogLevel('INFO')
    
    if '-r' in sys.argv or '--restart-on-offline' in sys.argv:
        QQBot().LoopForever()
    else:
        bot = QQBot()
        bot.Login()
        bot.Run()

class RequestError(Exception):
    pass

class QQBot:
    def LoopForever(self, userName=None):
        try:
            conf = Conf.getConf(userName)
            while True:
                self.login(conf)
                if self.Run() == 0:
                    break
                del self.__dict__[:]
        except KeyboardInterrupt:
            pass        
        except SystemExit as e:
            sys.exit(e)    
        except:
            ERROR('', exc_info=True)
            ERROR('QQBOT 发生未知错误，停止运行')
    
    def Login(self, userName=None): 
        self.login(Conf.getConf(userName))
    
    def login(self, conf):
        if conf['autoLogin'] is None:
            self.manualLogin(conf)
        else:
            try:
                self.autoLogin(qqNum=conf['autoLogin'])
            except Exception as e:
                if not isinstance(e, RequestError):
                    DEBUG('', exc_info=True)
                WARN('自动登录失败，改用手动登录')
                self.manualLogin(conf)

        INFO('登录成功。登录账号：%s (%d)', self.nick, self.qqNum)

    def manualLogin(self, conf):
        self.prepareSession()
        self.waitForAuth(conf)
        self.getPtwebqq()
        self.getVfwebqq()
        self.getUinAndPsessionid()
        self.testLogin()
        self.fetchBuddies()
        self.fetchGroups()
        self.fetchDiscusses()
        self.dumpSessionInfo()

    def autoLogin(self, qqNum):
        self.loadSessionInfo(qqNum)
        self.testLogin()

    def dumpSessionInfo(self):
        self.pollSession = pickle.loads(pickle.dumps(self.session))
        pickleFile = '%s-%s.pickle' % (QQBotVersion[:4], self.qqNum)
        picklePath = os.path.join(TmpDir, pickleFile)
        try:
            with open(picklePath, 'wb') as f:
                pickle.dump(self.__dict__, f)
        except IOError:
            DEBUG('', exc_info=True)
            WARN('保存 Session info 失败')
        else:
            INFO('Session info 已保存至文件：file://%s' % picklePath)

    def loadSessionInfo(self, qqNum):
        pickleFile = '%s-%s.pickle' % (QQBotVersion[:4], qqNum)
        picklePath = os.path.join(TmpDir, pickleFile)
        try:
            with open(picklePath, 'rb') as f:
                self.__dict__ = pickle.load(f)
        except IOError:
            DEBUG('', exc_info=True)
            ERROR('恢复 Session info 失败')
            raise
        else:
            INFO('成功从文件 file://%s 中恢复 Session info' % picklePath)

    def prepareSession(self):
        self.clientid = 53999199
        self.msgId = 6000000
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.9;'
                           ' rv:27.0) Gecko/20100101 Firefox/27.0'),
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        })
        self.urlGet(
            'https://ui.ptlogin2.qq.com/cgi-bin/login?daid=164&target=self&'
            'style=16&mibao_css=m_webqq&appid=501004106&enable_qlogin=0&'
            'no_verifyimg=1&s_url=http%3A%2F%2Fw.qq.com%2Fproxy.html&'
            'f_url=loginerroralert&strong_login=1&login_state=10&t=20131024001'
        )
        self.session.cookies.update({
            'RK': 'OfeLBai4FB',
            'pgv_pvi': '911366144',
            'pgv_info': 'ssid pgv_pvid=1051433466',
            'ptcz': ('ad3bf14f9da2738e09e498bfeb93dd9da7'
                     '540dea2b7a71acfb97ed4d3da4e277'),
            'qrsig': ('hJ9GvNx*oIvLjP5I5dQ19KPa3zwxNI'
                      '62eALLO*g2JLbKPYsZIRsnbJIxNe74NzQQ')
        })
        self.getAuthStatus()
        self.session.cookies.pop('qrsig')

    def waitForAuth(self, conf):
        qrcodeManager = QrcodeManager(conf)
        try:
            qrcodeManager.Show(self.getQrcode(), firstTime=True)
            while True:
                time.sleep(3)
                authStatus = self.getAuthStatus()
                if '二维码未失效' in authStatus:
                    INFO('登录 Step2 - 等待二维码扫描及授权')
                elif '二维码认证中' in authStatus:
                    INFO('二维码已扫描，等待授权')
                elif '二维码已失效' in authStatus:
                    WARN('二维码已失效, 重新获取二维码')
                    qrcodeManager.Show(self.getQrcode(), firstTime=False)
                elif '登录成功' in authStatus:
                    INFO('已获授权')
                    items = authStatus.split(',')
                    self.nick = items[-1].split("'")[1]
                    self.qqNum = int(self.session.cookies['superuin'][1:])
                    self.urlPtwebqq = items[2].strip().strip("'")
                    break
                else:
                    CRITICAL('获取二维码扫描状态时出错, html="%s"', authStatus)
                    sys.exit(1)
        finally:
            qrcodeManager.Destroy()

    def getQrcode(self, firstTime=True):
        INFO('登录 Step1 - 获取二维码')
        return self.urlGet(
            'https://ssl.ptlogin2.qq.com/ptqrshow?appid=501004106&e=0&l=M&' +
            's=5&d=72&v=4&t=' + repr(random.random())
        )

    def getAuthStatus(self):
        return self.urlGet(
            url='https://ssl.ptlogin2.qq.com/ptqrlogin?webqq_type=10&' +
                'remember_uin=1&login2qq=1&aid=501004106&u1=http%3A%2F%2F' +
                'w.qq.com%2Fproxy.html%3Flogin2qq%3D1%26webqq_type%3D10&' +
                'ptredirect=0&ptlang=2052&daid=164&from_ui=1&pttype=1&' +
                'dumy=&fp=loginerroralert&action=0-0-' +
                repr(random.random() * 900000 + 1000000) +
                '&mibao_css=m_webqq&t=undefined&g=1&js_type=0' +
                '&js_ver=10141&login_sig=&pt_randsalt=0',
            Referer=('https://ui.ptlogin2.qq.com/cgi-bin/login?daid=164&'
                     'target=self&style=16&mibao_css=m_webqq&appid=501004106&'
                     'enable_qlogin=0&no_verifyimg=1&s_url=http%3A%2F%2F'
                     'w.qq.com%2Fproxy.html&f_url=loginerroralert&'
                     'strong_login=1&login_state=10&t=20131024001')
        )

    def getPtwebqq(self):
        INFO('登录 Step3 - 获取ptwebqq')
        self.urlGet(self.urlPtwebqq)
        self.ptwebqq = self.session.cookies['ptwebqq']

    def getVfwebqq(self):
        INFO('登录 Step4 - 获取vfwebqq')
        self.vfwebqq = self.smartRequest(
            url = ('http://s.web2.qq.com/api/getvfwebqq?ptwebqq=%s&'
                   'clientid=%s&psessionid=&t=%s') %
                  (self.ptwebqq, self.clientid, repr(random.random())),
            Referer = ('http://s.web2.qq.com/proxy.html?v=20130916001'
                       '&callback=1&id=1'),
            Origin = 'http://s.web2.qq.com'
        )['vfwebqq']

    def getUinAndPsessionid(self):
        INFO('登录 Step5 - 获取uin和psessionid')
        result = self.smartRequest(
            url = 'http://d1.web2.qq.com/channel/login2',
            data = {
                'r': jsonDumps({
                    'ptwebqq': self.ptwebqq, 'clientid': self.clientid,
                    'psessionid': '', 'status': 'online'
                })
            },
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001'
                       '&callback=1&id=2'),
            Origin = 'http://d1.web2.qq.com'
        )
        self.uin = result['uin']
        self.psessionid = result['psessionid']
        self.hash = qHash(self.uin, self.ptwebqq)

    def testLogin(self):
        # 请求一下 get_online_buddies 页面，避免103错误。
        # 若请求无错误发生，则表明登录成功
        self.smartRequest(
            url = ('http://d1.web2.qq.com/channel/get_online_buddies2?'
                   'vfwebqq=%s&clientid=%d&psessionid=%s&t=%s') %
                  (self.vfwebqq, self.clientid,
                   self.psessionid, repr(random.random())),
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                       'callback=1&id=2'),
            Origin = 'http://d1.web2.qq.com',
            repeatOnDeny = 0
        )

    def fetchBuddies(self):
        INFO('登录 Step6 - 获取好友列表')
        result = self.smartRequest(
            url = 'http://s.web2.qq.com/api/get_user_friends2',
            data = {
                'r': jsonDumps({'vfwebqq':self.vfwebqq, 'hash':self.hash})
            },
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                       'callback=1&id=2')
        )
        ss, self.buddies, self.buddiesDictU, self.buddiesDictQ = [], [], {}, {}
        for info in result.get('info', []):
            uin = info['uin']
            name = info['nick']
            qq = self.smartRequest(
                url = ('http://s.web2.qq.com/api/get_friend_uin2?tuin=%d&'
                       'type=1&vfwebqq=%s&t=0.1') % (uin, self.vfwebqq),
                Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                           'callback=1&id=2')
            )['account']
            buddy = {'uin': uin, 'qq': qq, 'name': name}
            self.buddies.append(buddy)
            self.buddiesDictU[uin] = buddy
            self.buddiesDictQ[qq] = buddy
            s = '%d, %s, uin%d' % (qq, name, uin)
            INFO('好友： ' + s)
            ss.append(s)
        self.buddyStr = '好友列表:\n' + '\n'.join(ss)
        INFO('获取朋友列表成功，共 %d 个朋友' % len(self.buddies))

    def fetchGroups(self):
        INFO('登录 Step7 - 获取群列表')
        result = self.smartRequest(
            url = 'http://s.web2.qq.com/api/get_group_name_list_mask2',
            data = {
                'r': jsonDumps({'vfwebqq':self.vfwebqq, 'hash':self.hash})
            },
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                       'callback=1&id=2')
        )
        ss, self.groups, self.groupsDictU, self.groupsDictQ = [], [], {}, {}
        for info in result.get('gnamelist', []):
            uin = info['gid']
            name = info['name']
            qq = self.smartRequest(
                url = ('http://s.web2.qq.com/api/get_friend_uin2?tuin=%d&'
                       'type=4&vfwebqq=%s&t=0.1') % (uin, self.vfwebqq),
                Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                           'callback=1&id=2')
            )['account']
            group = {'uin': uin, 'qq': qq, 'name': name}
            self.groups.append(group)
            self.groupsDictU[uin] = group
            self.groupsDictQ[qq%1000000] = group
            s = '%d, %s, uin%d' % (qq, name, uin)
            INFO('群： ' + s)
            ss.append(s)
        self.groupStr = '群列表:\n' + '\n'.join(ss)
        INFO('获取群列表成功，共 %d 个朋友' % len(self.groups))

    def fetchDiscusses(self):
        INFO('登录 Step8 - 获取讨论组列表')
        result = self.smartRequest(
            url = ('http://s.web2.qq.com/api/get_discus_list?clientid=%s&'
                   'psessionid=%s&vfwebqq=%s&t=%s') % 
                  (self.clientid, self.psessionid,
                   self.vfwebqq, repr(random.random())),
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001'
                       '&callback=1&id=2')
        )
        ss, self.discusses, self.discussesDict = [], [], {}
        for info in result.get('dnamelist', []):
            uin = info['did']
            name = info['name']
            discuss = {'uin': uin, 'name': name}
            self.discusses.append(discuss)
            self.discussesDict[uin] = discuss
            s = '%s, uin%d' % (name, uin)
            INFO('讨论组： ' + s)
            ss.append(s)
        self.discussStr = '讨论组列表:\n' + '\n'.join(ss)
        INFO('获取讨论组列表成功，共 %d 个讨论组' % len(self.discusses))
    
    def getBuddyByUin(self, uin):
        return self.buddiesDictU[uin]
    
    def getBuddyByQq(self, qq):
        return self.buddiesDictQ[qq]
    
    def getGroupByUin(self, uin):
        return self.groupsDictU[uin]
    
    def getGroupByQq(self, qq):
        return self.groupsDictQ[qq%1000000]
    
    def getDiscussByUin(self, uin):
        return self.discussesDict[uin]

    def refetch(self):
        self.fetchBuddies()
        self.fetchGroups()
        self.fetchDiscusses()
        self.nick = self.fetchBuddyDetailInfo(self.uin)['nick']

    def fetchBuddyDetailInfo(self, uin):
        return self.smartRequest(
            url = ('http://s.web2.qq.com/api/get_friend_info2?tuin=%s&'
                   'vfwebqq=%s&clientid=%s&psessionid=%s&t=%s') %
                  (uin, self.vfwebqq, self.clientid,
                   self.psessionid, repr(random.random())),
            Referer = ('http://s.web2.qq.com/proxy.html?v=20130916001&'
                       'callback=1&id=1')
        )

    def poll(self):
        result = self.smartRequest(
            url = 'http://d1.web2.qq.com/channel/poll2',
            data = {
                'r': jsonDumps({
                    'ptwebqq':self.ptwebqq, 'clientid':self.clientid,
                    'psessionid':self.psessionid, 'key':''
                })
            },
            sessionObj = self.pollSession,
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                       'callback=1&id=2')
        )
        if 'errmsg' in result:
            pollResult = ('', 0, 0, '')  # 无消息
        else:
            result = result[0]
            msgType = {
                'message': 'buddy',
                'group_message': 'group',
                'discu_message': 'discuss'
            }[result['poll_type']]
            from_uin = result['value']['from_uin']
            buddy_uin = result['value'].get('send_uin', from_uin)
            msg = ''.join(
                ('[face%d]' % m[1]) if isinstance(m, list) else str(m)
                for m in result['value']['content'][1:]
            )
            pollResult = msgType, from_uin, buddy_uin, msg
            if msgType == 'buddy':
                INFO('来自 %s%d 的消息: "%s"' % (msgType, from_uin, msg))
            else:
                INFO('来自 %s%d(buddy%d) 的消息: "%s"' % pollResult)
        return pollResult

    def send(self, msgType, to_uin, msg):
        while msg:
            front, msg = utf8Partition(msg, 600)
            self._send(msgType, to_uin, front)

    def _send(self, msgType, to_uin, msg):
        self.msgId += 1
        if self.msgId % 10 == 0:
            INFO('已连续发送10条消息，强制 sleep 10秒，请等待...')
            time.sleep(10)
        else:
            time.sleep(random.randint(3,5))
        sendUrl = {
            'buddy': 'http://d1.web2.qq.com/channel/send_buddy_msg2',
            'group': 'http://d1.web2.qq.com/channel/send_qun_msg2',
            'discuss': 'http://d1.web2.qq.com/channel/send_discu_msg2'
        }
        sendTag = {'buddy':'to', 'group':'group_uin', 'discuss':'did'}
        self.smartRequest(
            url = sendUrl[msgType],
            data = {
                'r': jsonDumps({
                    sendTag[msgType]: to_uin,
                    'content': jsonDumps([
                        msg, ['font', {'name': '宋体', 'size': 10,
                                       'style': [0,0,0], 'color': '000000'}]
                    ]),
                    'face': 522,
                    'clientid': self.clientid,
                    'msg_id': self.msgId,
                    'psessionid': self.psessionid
                })
            },
            Referer = ('http://d1.web2.qq.com/proxy.html?v=20151105001&'
                       'callback=1&id=2')
        )
        INFO('向 %s%s 发送消息成功' % (msgType, to_uin))

    def urlGet(self, url, **kw):
        time.sleep(0.2)
        self.session.headers.update(kw)
        try:
            return self.session.get(url).content
        except (requests.exceptions.SSLError, AttributeError):
            return self.session.get(url, verify=False).content

    def smartRequest(self, url, data=None,
                     repeatOnDeny=2, sessionObj=None, **kw):
        session = sessionObj or self.session
        i, j = 0, 0
        while True:
            html = ''
            session.headers.update(**kw)
            try:
                if data is None:
                    resp = session.get(url)
                else:
                    resp = session.post(url, data=data)
                if resp.status_code == 502:
                    # 根据 'w.qq.com' 上的抓包记录，
                    # 当出现502错误时会 get 一下 ‘http://pinghot.qq.com/pingd’
                    session.get(
                        ('http://pinghot.qq.com/pingd?dm=w.qq.com.hot&url=/&'
                         'hottag=smartqq.im.polltimeout&hotx=9999&hoty=9999'
                         '&rand=%s') % random.randint(10000, 99999)
                    )
                    raise ValueError
                html = resp.content
                result = jsonLoads(html)
            except (requests.ConnectionError, ValueError):
                i += 1
                errorInfo = '网络错误或url地址错误'
            else:
                retcode = result.get('retcode', result.get('errCode', -1))
                if retcode in (0, 1202, 100003):
                    return result.get('result', result)
                else:
                    j += 1
                    errorInfo = '请求被拒绝错误'
            errMsg = '第%d次请求“%s”时出现“%s”，html=%s' % \
                     (i+j, url, errorInfo, repr(html))

            # 出现网络错误可以多试几次；
            # 若网络没问题，但 retcode 有误，一般连续 3 次都出错就没必要再试了
            if i <= 6 and j <= repeatOnDeny:
                DEBUG(errMsg + '\n    等待 3 秒后重新请求一次。')
                time.sleep(3)
            else:
                WARN(errMsg + '\n    停止再次请求！！！')
                raise RequestError

    # class attribute `helpInfo` will be printed at the start of `Run` method
    helpInfo = '帮助命令："-help"'

    def Run(self):
        self.msgQueue = Queue.Queue()
        self.stopped = False

        self.pullThread = threading.Thread(target=self.pullForever)
        self.pullThread.setDaemon(True)
        self.pullThread.start()

        INFO(
            'QQBot已启动，请用其他QQ号码向本QQ %s<%d> 发送命令来操作QQBot。%s' % \
            (self.nick,self.qqNum,self.__class__.__dict__.get('helpInfo',''))
        )

        while not self.stopped:
            try:
                pullResult = self.msgQueue.get()
                if pullResult is None:
                    break
                self.onPollComplete(*pullResult)
            except KeyboardInterrupt:
                self.stopped = True
            except RequestError:
                ERROR('向 QQ 服务器请求数据时出错')
                break
            except:
                WARN('', exc_info=True)
                WARN(' onPollComplete 方法出错，已忽略')

        if self.stopped:
            INFO('QQBot正常退出')
            return 0
        else:
            self.pullThread.join()
            ERROR('QQBot 已掉线')
            return 1

    def pullForever(self):
        while not self.stopped:
            try:
                pullResult = self.poll()
                self.msgQueue.put(pullResult)
            except KeyboardInterrupt:
                self.stopped = True
                self.msgQueue.put(None)
            except RequestError:
                ERROR('向 QQ 服务器请求数据时出错')
                self.msgQueue.put(None)
                break
            except:
                WARN('', exc_info=True)
                WARN(' poll 方法出错，已忽略')

    # override this method to build your own QQ-bot.
    def onPollComplete(self, msgType, from_uin, buddy_uin, message):
        if message == '-help':
            reply = ('欢迎使用QQBot，使用方法：\n'
                     '    -help\n'
                     '    -list buddy|group|discuss\n'
                     '    -send buddy|group|discuss {qq_or_uin} message\n'
                     '    -refetch\n'
                     '    -stop\n')

        elif message[:6] == '-list ':
            reply = getattr(self, message[6:].strip() + 'Str', '')

        elif message[:6] == '-send ':
            args = message[6:].split(' ', 2)
            if len(args) == 3 and args[1].isdigit() and \
                    args[0] in ('buddy', 'group', 'discuss'):
                n = int(args[1])
                try:
                    if args[0] == 'buddy':
                        uin = self.buddiesDictQ[n]['uin']
                    elif args[0] == 'group':
                        uin = self.groupsDictQ[n%1000000]['uin']
                    else:
                        uin = self.discussesDict[n]['uin']
                except KeyError:
                    reply = '接收者账号错误'
                else:
                    self.send(args[0], uin, args[2].strip())
                    reply = '消息发送成功'

        elif message == '-refetch':
            self.refetch()
            reply = '重新获取 好友/群/讨论组 成功'

        elif message == '-stop':
            reply = 'QQBot已关闭'
            self.stopped = True

        else:            
            reply = ''        

        self.send(msgType, from_uin, reply)

QQBot.configure()

def qHash(x, K):
    N = [0] * 4
    for T in range(len(K)):
        N[T%4] ^= ord(K[T])

    U, V = 'ECOK', [0] * 4
    V[0] = ((x >> 24) & 255) ^ ord(U[0])
    V[1] = ((x >> 16) & 255) ^ ord(U[1])
    V[2] = ((x >>  8) & 255) ^ ord(U[2])
    V[3] = ((x >>  0) & 255) ^ ord(U[3])

    U1 = [0] * 8
    for T in range(8):
        U1[T] = N[T >> 1] if T % 2 == 0 else V[T >> 1]

    N1, V1 = '0123456789ABCDEF', ''
    for aU1 in U1:
        V1 += N1[((aU1 >> 4) & 15)]
        V1 += N1[((aU1 >> 0) & 15)]

    return V1

def utf8Partition(msg, n):
    if n >= len(msg):
        return msg, ''
    else:
        # All utf8 characters start with '0xxx-xxxx' or '11xx-xxxx'
        while n > 0 and ord(msg[n]) >> 6 == 2:
            n -= 1
        return msg[:n], msg[n:]

if __name__ == '__main__':
    main()
