#!/usr/bin/env python3
"""
PDF简历处理脚本
智能提取PDF文字内容：
1. 文字PDF：使用PyPDF2直接提取
2. 图片PDF：使用阿里云qwen-vl-plus多模态模型提取，然后用qwen LLM优化结果
3. 最终用qwen LLM优化格式，并保存到对应用户的简历中
"""

import os
import sys
import django
import base64
from pathlib import Path
from io import BytesIO
# 添加项目路径到sys.path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / 'interview_backend'))

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'interview_backend.settings')
django.setup()

import pymongo
from dotenv import load_dotenv
from bson.objectid import ObjectId
from tqdm import tqdm
from interview.llm import qwen_model
from openai import OpenAI

# 加载环境变量
load_dotenv()

# 初始化OpenAI客户端
openai_client = OpenAI(api_key=os.getenv("ALIYUN_API_KEY"),base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

def get_db():
    """获取MongoDB数据库连接"""
    client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
    db = client[os.getenv("MONGODB_DB")]
    return db, client

def extract_text_from_pdf(pdf_path):
    """
    从PDF文件中提取文字内容，支持文字PDF和图片PDF（OCR）
    使用PyPDF2提取原始文本，如果失败则使用OCR，然后用qwen优化格式
    """
    try:
        # 首先使用PyPDF2提取原始文本
        import PyPDF2
        raw_text = ""

        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text.strip():
                    raw_text += page_text + "\n"

        # 如果PyPDF2提取到了足够的文本，直接使用
        if raw_text.strip() and len(raw_text.strip()) > 100:
            print(f"使用PyPDF2提取到文本 ({len(raw_text)} 字符)")
        else:
            # 如果PyPDF2提取的文本很少，尝试LLM Vision
            print(f"PyPDF2提取文本不足 ({len(raw_text)} 字符)，尝试LLM Vision...")
            ocr_text = extract_text_with_llm_vision(pdf_path)
            if ocr_text and ocr_text.strip():
                raw_text = ocr_text
                print(f"LLM Vision提取成功 ({len(raw_text)} 字符)")

                # 使用qwen优化LLM Vision结果
                try:
                    print("使用qwen优化LLM Vision文本...")
                    optimize_prompt = f"""请优化以下从图片中提取的简历文本内容。虽然已经是LLM Vision识别的结果，但可能仍有一些格式问题，请改善可读性，但保持所有原始信息：

LLM Vision文本：
{raw_text}

要求：
1. 保持所有个人信息、教育背景、工作经验、技能、项目经历等原始信息
2. 改进文本格式，使其更易阅读
3. 去除多余的换行符和空格
4. 整理段落结构
5. 不要添加任何不存在的信息
6. 不要删除任何重要信息

请返回优化后的简历文本："""

                    optimize_response = qwen_model.invoke(optimize_prompt)
                    optimized_ocr_text = optimize_response.content.strip()

                    if optimized_ocr_text and len(optimized_ocr_text) > len(raw_text) * 0.5:
                        raw_text = optimized_ocr_text
                        print(f"qwen优化LLM Vision文本成功 ({len(raw_text)} 字符)")
                    else:
                        print("qwen优化结果不可用，使用原始LLM Vision文本")

                except Exception as e:
                    print(f"qwen优化LLM Vision文本失败: {str(e)}，使用原始LLM Vision文本")

            else:
                print(f"警告: {pdf_path} LLM Vision也未能提取到有效文本")
                return None

        # 使用qwen优化和格式化文本
        try:
            prompt = f"""请优化以下从PDF简历中提取的文本内容，保持原始信息完整性，但改善格式和可读性：

原始文本：
{raw_text}

要求：
1. 保持所有个人信息、教育背景、工作经验、技能、项目经历等原始信息
2. 改进文本格式，使其更易阅读
3. 去除多余的换行符和空格
4. 整理段落结构
5. 不要添加任何不存在的信息
6. 不要删除任何重要信息

请返回优化后的简历文本："""

            response = qwen_model.invoke(prompt)
            optimized_text = response.content.strip()

            if optimized_text:
                return optimized_text
            else:
                print(f"qwen处理失败，使用原始文本")
                return raw_text.strip()

        except Exception as e:
            print(f"qwen优化失败，使用原始文本: {str(e)}")
            return raw_text.strip()

    except ImportError:
        print("错误: 未安装PyPDF2库，请运行: pip install PyPDF2")
        return None
    except Exception as e:
        print(f"提取PDF文本时出错 {pdf_path}: {str(e)}")
        return None

def extract_text_with_llm_vision(pdf_path):
    """
    使用阿里云qwen-vl-plus多模态模型从PDF中提取文字（适用于图片格式的PDF）
    """
    try:
        from pdf2image import convert_from_path

        # 将PDF转换为图片
        print(f"正在将PDF转换为图片进行qwen-vl-plus识别: {pdf_path}")
        images = convert_from_path(pdf_path, dpi=200)  # 适当的DPI平衡质量和速度

        extracted_text = ""
        for i, image in enumerate(images):
            print(f"正在使用qwen-vl-plus处理第{i+1}页...")

            try:
                # 将图片转换为base64
                buffer = BytesIO()
                image.save(buffer, format="JPEG")
                image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

                # 使用阿里云qwen-vl-plus多模态模型
                response = openai_client.chat.completions.create(
                    model="qwen-vl-plus",  # 使用支持多模态的模型
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "请从这张图片中提取所有文字内容。这是一个简历文件，请准确提取个人信息、教育背景、工作经验、技能、项目经历等所有文字内容。保持原始格式，不要遗漏任何信息。"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=4000,
                    temperature=0.1
                )

                page_text = response.choices[0].message.content.strip()
                if page_text:
                    extracted_text += page_text + "\n"
                    print(f"LLM Vision提取成功 ({len(page_text)} 字符)")
                else:
                    print(f"LLM Vision未提取到文本")

            except Exception as e:
                print(f"LLM Vision处理第{i+1}页失败: {str(e)}")
                continue

        return extracted_text.strip() if extracted_text.strip() else None

    except ImportError as e:
        print(f"PDF转图片依赖未安装: {str(e)}")
        print("请安装: pip install pdf2image pillow")
        return None
    except Exception as e:
        print(f"LLM Vision处理失败: {str(e)}")
        return None

def get_user_by_name(db, name):
    """根据用户名查找用户"""
    users_collection = db['users']
    user = users_collection.find_one({'name': name})
    return user

def update_user_resume(db, user_id, resume_content):
    """更新用户的简历，直接覆盖原有内容"""
    resumes_collection = db['resumes']

    # 直接覆盖简历内容
    result = resumes_collection.update_one(
        {'_id': user_id},
        {'$set': {'content': resume_content}},
        upsert=True
    )

    return result

def process_pdf_files():
    """处理归档文件夹中的所有PDF文件"""
    # 获取数据库连接
    db, mongo_client = get_db()

    # PDF文件目录
    archive_dir = project_root / "归档"

    # 获取所有PDF文件
    pdf_files = list(archive_dir.glob("*-自荐信.pdf"))

    print(f"找到 {len(pdf_files)} 个PDF文件待处理")
    print("警告: 此脚本将直接覆盖数据库中现有的简历内容!")
    print("=" * 50)

    # 统计信息
    processed_count = 0
    success_count = 0
    error_count = 0

    # 使用进度条处理文件
    for pdf_file in tqdm(pdf_files, desc="处理PDF文件"):
        try:
            # 从文件名提取用户名（去掉"-自荐信.pdf"部分）
            filename = pdf_file.name
            user_name = filename.replace("-自荐信.pdf", "")

            print(f"\n处理用户: {user_name}")

            # 查找用户
            user = get_user_by_name(db, user_name)
            if not user:
                print(f"未找到用户: {user_name}")
                error_count += 1
                continue

            # 提取PDF文字
            extracted_text = extract_text_from_pdf(str(pdf_file))
            if not extracted_text:
                print(f"提取文字失败: {user_name}")
                error_count += 1
                continue

            # 检查是否已有简历内容
            resumes_collection = db['resumes']
            existing_resume = resumes_collection.find_one({'_id': user['_id']})
            if existing_resume and existing_resume.get('content'):
                print(f"警告: 将覆盖用户 {user_name} 的现有简历内容")
            else:
                print(f"创建新简历: {user_name}")

            # 更新用户简历（直接覆盖）
            user_id = user['_id']
            result = update_user_resume(db, user_id, extracted_text)

            if result.acknowledged:
                print(f"成功更新用户简历: {user_name}")
                success_count += 1
            else:
                print(f"更新简历失败: {user_name}")
                error_count += 1

            processed_count += 1

        except Exception as e:
            print(f"处理文件 {pdf_file.name} 时发生错误: {str(e)}")
            error_count += 1

    # 关闭数据库连接
    mongo_client.close()

    # 输出统计结果
    print("处理完成!")
    print(f"总文件数: {len(pdf_files)}")
    print(f"成功处理: {success_count}")
    print(f"处理失败: {error_count}")

if __name__ == "__main__":
    # 检查环境变量
    if not os.getenv("MONGODB_URI"):
        print("错误: 未设置MONGODB_URI环境变量")
        sys.exit(1)

    if not os.getenv("MONGODB_DB"):
        print("错误: 未设置MONGODB_DB环境变量")
        sys.exit(1)


    if not os.getenv("ALIYUN_API_KEY"):
        print("错误: 未设置ALIYUN_API_KEY环境变量")
        sys.exit(1)

    process_pdf_files()
