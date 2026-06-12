"""
测试脚本 - 向后端发送消息请求
"""
import urllib.request
import urllib.error
import json
import sys

def send_message(message: str, base_url: str = "http://127.0.0.1:8000") -> dict:
    """
    发送消息到后端

    Args:
        message: 消息内容
        base_url: 后端地址

    Returns:
        响应结果
    """
    url = f"{base_url}/api/message"

    data = {
        "message": message
    }

    json_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=json_data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            return {"success": True, "data": result}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    test_message = "帮我用wiki查询一下乐魂的信息"

    print(f"发送测试请求: {test_message}")
    print("-" * 60)

    result = send_message(test_message)

    if result["success"]:
        print(f"[OK] Success!")
        print(f"Response: {result['data']}")
    else:
        print(f"[FAIL] Failed!")
        print(f"Error: {result['error']}")
        sys.exit(1)
