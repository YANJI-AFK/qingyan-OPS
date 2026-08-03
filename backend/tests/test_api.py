import requests, time

url = "http://127.0.0.1:5000/chat"
tests = ["打开监控大屏", "打开监控", "跳转到工单列表", "有多少未完成的工单", "CPU使用率多少"]

for t in tests:
    try:
        r = requests.post(url, json={"text": t}, timeout=20)
        d = r.json()
        action = d.get("action") or "-"
        target = d.get("target") or "-"
        reply = d.get("reply_text", "")
        print(f"{t:20s} | action={str(action):10s} | target={str(target):15s} | {reply[:60]}")
    except Exception as e:
        print(f"{t:20s} | ERROR: {e}")
    time.sleep(1)
