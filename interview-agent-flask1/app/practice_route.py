import json
import os
import time
from datetime import datetime
from io import BytesIO

import docx
import PyPDF2
from flask import Blueprint, request, Response, jsonify

from services.DeepSeek import DeepseekAPI
from services.SparkPractice import AIPracticeAPI


practice_bp = Blueprint('practice', __name__)


@practice_bp.route('/answer', methods=['GET'])
def handle_answer():
    """Handle answer request with simulated streaming response."""
    user_message = request.args.get('page', default=1, type=str)
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    def generate_response():
        """Generate simulated streaming response."""
        responses = [
            '正在分析您的问题...\n',
            '根据您的描述，我认为...\n',
            '以下是我的建议：\n',
            '1. 首先...\n',
            '2. 其次...\n',
            '3. 最后...\n'
        ]
        for response in responses:
            time.sleep(0.5)  # 模拟处理延迟
            yield response.encode('utf-8')
    
    return Response(generate_response(), mimetype='text/event-stream')


@practice_bp.route('/answer_v1', methods=['GET'])
def handle_answer_v1():
    """Handle answer request using AI practice API."""
    user_message = request.args.get('prompt', default="", type=str)
    
    if not user_message:
        return jsonify({'error': 'No message provided'}), 400
    
    try:
        ai_practice = AIPracticeAPI.getInstance()
        response = ai_practice.get_answer(user_message)
        
        if response:
            return jsonify({'content': response})
        else:
            return jsonify({'error': 'AI Practice API error'}), 500
    except Exception as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500
    

@practice_bp.route('/evaluate', methods=['GET'])
def evaluate():
    """Evaluate user performance based on history data."""
    history_data = request.args.get('historyData', default="", type=str)
    
    if not history_data:
        return jsonify({'error': 'No history_data provided'}), 400
    
    prompt = f'''请根据我的根据历史刷题记录分析我的薄弱环节、高频错误点，并给出针对性的提升策略（如知识点、相关知识等）。要求分析简洁清晰，针对性强。
                以下是我的历史刷题记录：
                <{history_data}>
             '''
    
    try:
        deepseek = DeepseekAPI.getInstance()
        response = deepseek.safe_generate_content_deepseek2(prompt)
        
        if response:
            return jsonify({'content': response.text})
        else:
            return jsonify({'error': 'Deepseek API error'}), 500
    except Exception as e:
        return jsonify({'error': f'API request failed: {str(e)}'}), 500

@practice_bp.route('/evaluate_v2', methods=['GET'])
def evaluate_stream():
    """Evaluate user performance with streaming response."""
    history_data = request.args.get('historyData', default="", type=str)
    
    if not history_data:
        return jsonify({'error': 'No history_data provided'}), 400
    
    prompt = f'''请根据我的根据历史刷题记录分析我的薄弱环节、高频错误点，并给出针对性的提升策略（如重点练习哪些题型、时间管理建议等）。要求分析简洁清晰，建议可操作性强。
                以下是我的历史刷题记录：
                <{history_data}>
             '''
    
    def generate():
        """Generate streaming response from DeepSeek API."""
        try:
            stream = DeepseekAPI.getInstance().global_deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield f"data: {chunk.choices[0].delta.content}\n\n"
        except Exception as e:
            yield f"data: Error: {str(e)}\n\n"
    
    return Response(
        generate(), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        }
    )


@practice_bp.route('/resume', methods=['POST'])
def handle_resume():
    """Handle resume file upload and analysis."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Define the prompt template
    prompt_template = '''你是一名资深职业规划师，请根据用户提供的简历内容，按以下要求输出优化建议：
        ## 输出规则
        1. **格式要求**：必须使用Markdown结构化输出
        2. **长度控制**：每条建议不超过3句话，总输出不超过400字
        3. **内容分级**：按优先级标注（❗关键项 / ⚠️改进项 / 💡加分项）
        4. **禁止事项**：不得出现"建议优化"等模糊表述，必须给出具体修改方案
        结尾不要出现"字数统计等字眼"
        '''
    
    try:
        content = _extract_file_content(file)
        if not content:
            return jsonify({'error': 'Failed to extract content from file'}), 400
        
        # Save resume content to local file
        saved_file_path = _save_resume_content(content)
        
        # Generate analysis using DeepSeek API
        full_prompt = f"{prompt_template}，以下是简历内容：{content}"
        deepseek = DeepseekAPI.getInstance()
        response = deepseek.safe_generate_content_deepseek2(full_prompt)
        
        if response:
            return jsonify({'content': response.text})
        else:
            return jsonify({'error': 'Deepseek API error'}), 500
            
    except Exception as e:
        return jsonify({'error': f'File processing failed: {str(e)}'}), 500


def _extract_file_content(file):
    """Extract content from uploaded file (PDF or DOCX)."""
    content = ''
    
    try:
        if file.filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(BytesIO(file.read()))
            for page in pdf_reader.pages:
                content += page.extract_text() + '\n'
        elif file.filename.endswith('.docx'):
            doc = docx.Document(BytesIO(file.read()))
            content = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
        else:
            raise ValueError('Invalid file type. Only PDF and DOCX files are allowed.')
    except Exception as e:
        raise Exception(f'Failed to extract content: {str(e)}')
    
    return content


def _save_resume_content(content):
    """Save resume content to local file with timestamp."""
    try:
        save_dir = os.path.join(os.path.dirname(__file__), '..', 'resource', 'resume')
        os.makedirs(save_dir, exist_ok=True)
        
        timestamp = int(time.time())
        filename = f"resume-{timestamp}.txt"
        file_path = os.path.join(save_dir, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return file_path
    except Exception as e:
        raise Exception(f'Failed to save resume content: {str(e)}')
