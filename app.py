import urllib.parse  # 【必加】URL编码，解决latin-1编码问题
from flask import Flask, request, jsonify, make_response, render_template, send_file
import sqlite3
import time
import pandas as pd
from io import BytesIO
import functools  # 新增：导入functools模块

app = Flask(__name__)
# 数据库文件路径
DB_FILE = "user_info.db"

# 初始化数据库（首次运行自动创建表，含唯一MAC校验基础）


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 表结构：id(主键)、user_name(姓名)、ip_addr(IP地址)、mac_addr(MAC地址，核心唯一标识)、create_time(创建时间)、update_time(更新时间)
    c.execute('''CREATE TABLE IF NOT EXISTS user_info
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_name TEXT NOT NULL,
                  ip_addr TEXT NOT NULL,
                  mac_addr TEXT NOT NULL,
                  nic_type TEXT DEFAULT '未知网卡',
                  create_time TEXT NOT NULL,
                  update_time TEXT NOT NULL)''')
    conn.commit()
    conn.close()

# 数据库连接装饰器（简化重复连接代码，修复endpoint冲突）


def db_connect(func):
    @functools.wraps(func)  # 核心修复：继承原函数元信息，避免endpoint覆盖
    def wrapper(*args, **kwargs):
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # 让查询结果支持字典式访问
        c = conn.cursor()
        result = func(c, conn, *args, **kwargs)
        conn.close()
        return result
    return wrapper

# 客户端采集页


@app.route('/')
def index():
    return render_template('index.html')

# 核心接口：接收客户端数据，MAC存在则更新，否则新增


@app.route('/upload', methods=['POST'])
@db_connect
def upload(c, conn):
    try:
        # 获取前端提交的JSON数据
        user_name = request.json.get('user_name')
        ip_addr = request.json.get('ip_addr')
        mac_addr = request.json.get('mac_addr')
        nic_type = request.json.get('nic_type', '未知网卡')  # 新增：获取网卡类型，默认未知

        # 基础参数校验
        if not all([user_name, ip_addr, mac_addr, nic_type]):
            return jsonify({'code': 400, 'msg': '参数错误：姓名/IP/MAC/网卡类型不能为空'})

        # 获取当前时间（格式：年-月-日 时:分:秒）
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

        # 校验MAC地址是否已存在
        c.execute('SELECT id FROM user_info WHERE mac_addr = ?', (mac_addr,))
        exists = c.fetchone()

        if exists:
            # MAC存在：执行更新操作（更新姓名、IP、更新时间）
            c.execute('''UPDATE user_info SET user_name = ?, ip_addr = ?, nic_type = ?, update_time = ?
             WHERE mac_addr = ?''', (user_name, ip_addr, nic_type, current_time, mac_addr))
            conn.commit()
            return jsonify({'code': 200, 'msg': '数据已更新（MAC地址重复）'})
        else:
            # MAC不存在：执行新增操作
            c.execute('''INSERT INTO user_info (user_name, ip_addr, mac_addr, nic_type, create_time, update_time)
             VALUES (?, ?, ?, ?, ?, ?)''', (user_name, ip_addr, mac_addr, nic_type, current_time, current_time))
            conn.commit()
            return jsonify({'code': 200, 'msg': '数据新增成功'})
    except Exception as e:
        return jsonify({'code': 500, 'msg': f'服务器错误：{str(e)}'})

# 服务端：查询所有数据


@app.route('/query/all', methods=['GET'])
@db_connect
def query_all(c, conn):
    c.execute('SELECT * FROM user_info ORDER BY create_time DESC')
    rows = c.fetchall()
    # 转换为列表字典格式，方便前端渲染
    data = [dict(row) for row in rows]
    return jsonify({'code': 200, 'data': data})

# 服务端：条件查询（支持按姓名/IP/MAC模糊查询）


@app.route('/query/condition', methods=['GET'])
@db_connect
def query_condition(c, conn):
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'code': 400, 'msg': '查询关键词不能为空'})
    # 模糊查询：姓名/IP/MAC包含关键词
    c.execute('''SELECT * FROM user_info
                 WHERE user_name LIKE ? OR ip_addr LIKE ? OR mac_addr LIKE ?
                 ORDER BY create_time DESC''',
              (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
    rows = c.fetchall()
    data = [dict(row) for row in rows]
    return jsonify({'code': 200, 'data': data})

# 服务端：修改单条数据（按ID修改）


@app.route('/update/<int:user_id>', methods=['PUT'])
@db_connect
def update_by_id(c, conn, user_id):
    try:
        data = request.get_json()
        user_name = data.get('user_name', '').strip()
        ip_addr = data.get('ip_addr', '').strip()
        mac_addr = data.get('mac_addr', '').strip()
        nic_type = data.get('nic_type', '').strip()

        if not all([user_name, ip_addr, mac_addr, nic_type]):
            return jsonify({'code': 400, 'msg': '参数错误：姓名/IP/MAC/网卡类型不能为空'})

        # 校验除当前ID外，MAC是否重复（避免修改后MAC冲突）
        c.execute(
            'SELECT id FROM user_info WHERE mac_addr = ? AND id != ?', (mac_addr, user_id))
        if c.fetchone():
            return jsonify({'code': 400, 'msg': 'MAC地址已存在，无法修改'})

        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        c.execute('''UPDATE user_info
                     SET user_name = ?, ip_addr = ?, mac_addr = ?, nic_type = ?, update_time = ?
                     WHERE id = ?''',
                  (user_name, ip_addr, mac_addr, nic_type, current_time, user_id))
        conn.commit()
        if c.rowcount == 0:
            return jsonify({'code': 404, 'msg': '数据不存在'})
        return jsonify({'code': 200, 'msg': '数据修改成功'})
    except Exception as e:
        return jsonify({'code': 500, 'msg': f'服务器错误：{str(e)}'})

# 服务端：删除单条数据（按ID删除）


@app.route('/delete/<int:user_id>', methods=['DELETE'])
@db_connect
def delete_by_id(c, conn, user_id):
    c.execute('DELETE FROM user_info WHERE id = ?', (user_id,))
    conn.commit()
    if c.rowcount == 0:
        return jsonify({'code': 404, 'msg': '数据不存在'})
    return jsonify({'code': 200, 'msg': '数据删除成功'})


# 服务端：导出数据库所有数据为Excel文件（最终修复版，解决keep_vba参数错误）
@app.route('/export/excel', methods=['GET'])
@db_connect
def export_excel(c, conn):
    try:
        c.execute('SELECT * FROM user_info ORDER BY create_time DESC')
        rows = c.fetchall()
        if not rows:
            return jsonify({'code': 400, 'msg': '无数据可导出'}), 400  # 规范HTTP状态码

        # 转换为列表字典（兼容sqlite3.Row的字典格式）
        data = [dict(row) for row in rows]
        df = pd.DataFrame(data)

        # 1. 强制指定列顺序，避免列乱序
        df = df[['id', 'user_name', 'nic_type', 'ip_addr',
                 'mac_addr', 'create_time', 'update_time']]
        if 'mac_addr' in df.columns:  # 容错判断，避免列不存在报错
            # 核心逻辑：先去所有-，再转小写，兼容空值/异常格式
            df['mac_addr'] = df['mac_addr'].apply(
                lambda x: x.replace("-", "").lower() if pd.notna(x) else x)

        # 2. 重命名列名（中文），适配Excel展示
        df.columns = ['序号', '用户姓名', '网卡类型', 'IP地址', 'MAC地址', '创建时间', '更新时间']

        # 3. Excel写入（原有逻辑，无修改，已修复keep_vba/指针问题）
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='用户网卡信息', index=False, header=True)
        output.seek(0)  # 重置文件指针，必须保留，避免文件损坏

        # ---------------------- 核心修复：Flask官方适配的文件名+响应头（解决latin-1编码） ----------------------
        # 步骤1：生成原始中文文件名，三层兜底确保永不空白
        try:
            raw_filename = f"{time.strftime('%Y%m%d%H%M%S', time.localtime())}.xlsx"
        except:
            raw_filename = f"{time.strftime('%Y%m%d')}.xlsx"
        finally:
            raw_filename = raw_filename or "用户信息导出.xlsx"

        # 步骤2：URL全编码中文文件名（Flask官方推荐，转为latin-1可识别的%xx格式）
        encode_filename = urllib.parse.quote(
            raw_filename, safe='')  # safe=''表示编码所有特殊字符

        # 步骤3：使用 Flask 的 send_file 来生成带正确编码的下载响应，兼容各浏览器
        output.seek(0)
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        try:
            # Flask >= 2.0 使用 download_name
            return send_file(output, mimetype=mimetype, as_attachment=True, download_name=raw_filename)
        except TypeError:
            # 兼容旧版 Flask，回退到 attachment_filename 参数
            return send_file(output, mimetype=mimetype, as_attachment=True, attachment_filename=raw_filename)

    except Exception as e:
        # 打印详细错误日志，方便排查
        print(f"Excel导出失败详细错误：{str(e)}")
        return jsonify({'code': 500, 'msg': f'导出失败：{str(e)[:50]}'}), 500

# 服务端数据管理页


@app.route('/manage')
def manage():
    return render_template('manage.html')


# 程序入口：初始化数据库+启动服务
if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
