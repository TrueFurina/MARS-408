import zlib, struct, base64, json, urllib.request, urllib.error
def make_png(w,h,rgb):
    raw=b''
    for y in range(h):
        raw+=b'\x00'+bytes(rgb)*w
    def chunk(typ,data):
        c=typ+data
        return struct.pack('>I',len(data))+c+struct.pack('>I',zlib.crc32(c)&0xffffffff)
    sig=b'\x89PNG\r\n\x1a\n'
    ihdr=struct.pack('>IIBBBBB',w,h,8,2,0,0,0)
    idat=zlib.compress(raw)
    return sig+chunk(b'IHDR',ihdr)+chunk(b'IDAT',idat)+chunk(b'IEND',b'')
img=make_png(96,96,(120,160,220))
b64=base64.b64encode(img).decode()
req=urllib.request.Request("http://127.0.0.1:8002/api/auth/login",data=json.dumps({"username":"demo","password":"demo123456"}).encode(),headers={"Content-Type":"application/json"},method="POST")
tok=json.loads(urllib.request.urlopen(req,timeout=10).read())["token"]
body=json.dumps({"image_base64":b64,"question":"这张图片主要是什么颜色？"}).encode()
req2=urllib.request.Request("http://127.0.0.1:8002/api/xfyun/image-understand",data=body,headers={"Content-Type":"application/json","Authorization":f"Bearer {tok}"},method="POST")
try:
    with urllib.request.urlopen(req2,timeout=60) as r:
        print("STATUS",r.status)
        print(r.read().decode()[:600])
except urllib.error.HTTPError as e:
    print("HTTP",e.code,e.read().decode()[:600])
except Exception as e:
    print("ERR",e)
