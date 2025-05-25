from flask import Flask, jsonify, request
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, quote
import time
from datetime import datetime
import json

app = Flask(__name__)

class MegaNormAPI:
    def __init__(self):
        self.base_url = "https://meganorm.ru"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def get_page(self, url, retries=3):
        """Получение страницы с повторными попытками"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                response.encoding = 'utf-8'
                return response
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise e
                time.sleep(2)
    
    def clean_text(self, text):
        """Очистка текста от лишних символов и форматирование"""
        if not text:
            return ""
        
        # Удаление лишних пробелов и переносов
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Удаление специальных символов, которые могут вызвать проблемы с JSON
        text = text.replace('\x00', '').replace('\ufeff', '')
        
        # Ограничение длины текста для предотвращения слишком больших ответов
        # if len(text) > 50000:  # Ограничиваем 50KB текста
        #     text = text[:50000] + "... [текст обрезан]"
        
        return text
    
    def parse_document_list(self, url):
        """Парсинг списка документов"""
        try:
            response = self.get_page(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            documents = []
            
            # Улучшенный поиск ссылок на документы
            doc_selectors = [
                'a[href*="/mega_doc/"]',
                '.doc-link',
                '.document-link',
                'a[href*="gost"]',
                'a[href*="federalnyj-zakon"]',
                'a[href*="prikaz"]',
                'a[href*="postanovlenie"]'
            ]
            
            doc_links = []
            for selector in doc_selectors:
                found_links = soup.select(selector)
                doc_links.extend(found_links)
            
            # Удаление дубликатов
            seen_urls = set()
            unique_links = []
            for link in doc_links:
                href = link.get('href')
                if href and href not in seen_urls and not href.endswith('_0.html'):
                    seen_urls.add(href)
                    unique_links.append(link)
            
            for link in unique_links[:100]:  # Ограничиваем количество для производительности
                doc_info = self.extract_document_info_from_link(link)
                if doc_info:
                    documents.append(doc_info)
            
            return documents
            
        except Exception as e:
            raise Exception(f"Ошибка при парсинге списка документов: {str(e)}")
    
    def extract_document_info_from_link(self, link):
        """Извлечение информации о документе из ссылки"""
        try:
            href = link.get('href')
            if not href:
                return None
                
            full_url = urljoin(self.base_url, href)
            
            # Извлечение названия из текста ссылки
            title = self.clean_text(link.get_text(strip=True))
            if not title or len(title) < 3:
                return None
            
            # Определение типа документа по URL
            doc_type = self.determine_document_type(href)
            
            # Извлечение номера документа из URL или названия
            doc_number = self.extract_document_number(href, title)
            
            return {
                "title": title,
                "url": full_url,
                "type": doc_type,
                "number": doc_number,
                "relative_url": href
            }
            
        except Exception as e:
            print(f"Ошибка извлечения информации о документе: {str(e)}")
            return None
    
    def determine_document_type(self, url):
        """Определение типа документа по URL"""
        url_lower = url.lower()
        if '/gost' in url_lower or '/standart' in url_lower:
            return "ГОСТ"
        elif '/federalnyj-zakon' in url_lower:
            return "Федеральный закон"
        elif '/prikaz' in url_lower:
            return "Приказ"
        elif '/postanovlenie' in url_lower:
            return "Постановление"
        elif '/snip' in url_lower:
            return "СНиП"
        elif '/sp' in url_lower:
            return "СП"
        else:
            return "Документ"
    
    def extract_document_number(self, url, title):
        """Извлечение номера документа"""
        # Попытка извлечь номер из названия
        number_patterns = [
            r'№\s*(\d+[-/]\d+)',
            r'(\d{4,5}[-/]\d{4})',
            r'ГОСТ\s+Р?\s*(\d+(?:\.\d+)*[-/]\d+)',
            r'СП\s+(\d+(?:\.\d+)*)',
            r'СНиП\s+(\d+(?:\.\d+)*[-/]\d+)',
            r'(\d+\.\d+\.\d+)',
            r'(\d+-\d+)'
        ]
        
        combined_text = f"{title} {url}"
        
        for pattern in number_patterns:
            match = re.search(pattern, combined_text)
            if match:
                return match.group(1)
        
        return None
    
    def get_document_details(self, doc_url):
        """Получение детальной информации о документе"""
        try:
            response = self.get_page(doc_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Извлечение основной информации
            title = self.extract_title(soup)
            content_sections = self.extract_content_sections(soup)
            metadata = self.extract_metadata(soup, title)
            
            return {
                "title": title,
                "sections": content_sections,
                "metadata": metadata,
                "url": doc_url,
                "parsed_at": datetime.now().isoformat(),
                "status": "success"
            }
            
        except Exception as e:
            return {
                "error": f"Ошибка при получении деталей документа: {str(e)}",
                "url": doc_url,
                "status": "error",
                "parsed_at": datetime.now().isoformat()
            }
    
    def extract_title(self, soup):
        """Извлечение заголовка документа"""
        title_selectors = [
            'h1',
            '.document-title',
            '.doc-title',
            '.main-title',
            'title'
        ]
        
        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = self.clean_text(element.get_text())
                if title and len(title) > 5:
                    return title
        
        return "Документ без названия"
    
    def extract_content_sections(self, soup):
        """Извлечение содержимого документа по разделам"""
        # Удаление ненужных элементов
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            element.decompose()

        sections = []
    
        # Поиск основного содержимого
        content_selectors = [
            '.document-content',
            '.doc-content',
            '.main-content',
            'main',
            '.content',
            'article'
        ]
    
        main_content = None
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                main_content = element
                break
    
        if not main_content:
            main_content = soup.find('body')
    
        if main_content:
            # Поиск заголовков и разделов
            headings = main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
            if headings:
                current_section = {"title": "Введение", "content": ""}
    
                for element in main_content.descendants:
                    if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        # Сохраняем предыдущую секцию
                        if current_section["content"].strip():
                            current_section["content"] = self.clean_text(current_section["content"])
                            sections.append(current_section)
    
                        # Начинаем новую секцию
                        current_section = {
                            "title": self.clean_text(element.get_text()),
                            "content": ""
                        }
                    elif element.string and element.parent.name not in ['script', 'style']:
                        text = element.string.strip()
                        if text:
                            current_section["content"] += text + " "
    
                # Добавляем последнюю секцию
                if current_section["content"].strip():
                    current_section["content"] = self.clean_text(current_section["content"])
                    sections.append(current_section)
            else:
                # Если нет заголовков, добавляем весь контент как одну секцию
                full_text = self.clean_text(main_content.get_text(separator=' '))
                if full_text:
                    sections.append({
                        "title": "Содержание документа",
                        "content": full_text
                    })
    
        return sections  # Убираем ограничение на количество секций

    
    def extract_metadata(self, soup, title):
        """Извлечение метаданных документа"""
        metadata = {}
        
        text = soup.get_text()
        
        # Поиск даты принятия
        date_patterns = [
            r'от\s+(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{4}-\d{2}-\d{2})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['date'] = match.group(1)
                break
        
        # Поиск номера документа
        number_patterns = [
            r'№\s*([№\d\-/]+)',
            r'ГОСТ\s+Р?\s*(\d+(?:\.\d+)*[-/]\d+)',
            r'(\d{4,5}[-/]\d{4})'
        ]
        
        for pattern in number_patterns:
            match = re.search(pattern, f"{title} {text}")
            if match:
                metadata['number'] = match.group(1)
                break
        
        # Поиск статуса
        text_lower = text.lower()
        if 'действует' in text_lower:
            metadata['status'] = 'Действует'
        elif 'отменен' in text_lower or 'утратил силу' in text_lower:
            metadata['status'] = 'Не действует'
        else:
            metadata['status'] = 'Не определен'
        
        return metadata

# Инициализация API
api = MegaNormAPI()

@app.route('/api/documents/<doc_type>')
def get_documents_by_type(doc_type):
    """Получение списка документов по типу"""
    try:
        type_urls = {
            'gost': 'https://meganorm.ru/mega_doc/fire/standart/standart_0.html',
            'federal-laws': 'https://meganorm.ru/mega_doc/fire/federalnyj-zakon/federalnyj-zakon_0.html',
            'orders': 'https://meganorm.ru/mega_doc/fire/prikaz/prikaz_0.html',
            'resolutions': 'https://meganorm.ru/mega_doc/fire/postanovlenie/postanovlenie_0.html'
        }
        
        if doc_type not in type_urls:
            return jsonify({
                'error': 'Неподдерживаемый тип документа',
                'available_types': list(type_urls.keys())
            }), 400
        
        documents = api.parse_document_list(type_urls[doc_type])
        
        # Пагинация
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
        
        start = (page - 1) * per_page
        end = start + per_page
        
        return jsonify({
            'documents': documents[start:end],
            'total': len(documents),
            'page': page,
            'per_page': per_page,
            'pages': (len(documents) + per_page - 1) // per_page,
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/document')
def get_document_details():
    """Получение детальной информации о документе"""
    try:
        doc_url = request.args.get('url')
        if not doc_url:
            return jsonify({
                'error': 'Параметр url обязателен',
                'status': 'error'
            }), 400
        
        # Проверка, что URL относится к MegaNorm
        if not doc_url.startswith('https://meganorm.ru'):
            return jsonify({
                'error': 'URL должен принадлежать сайту meganorm.ru',
                'status': 'error'
            }), 400
        
        document = api.get_document_details(doc_url)
        
        # Проверяем, не произошла ли ошибка при парсинге
        if document.get('status') == 'error':
            return jsonify(document), 500
            
        return jsonify(document)
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error',
            'url': request.args.get('url', 'не указан')
        }), 500

@app.route('/api/search')
def search_documents():
    """Поиск документов по ключевым словам"""
    try:
        query = request.args.get('q', '').strip()
        doc_type = request.args.get('type', 'all')
        
        if not query:
            return jsonify({
                'error': 'Параметр q (поисковый запрос) обязателен',
                'status': 'error'
            }), 400
        
        if len(query) < 2:
            return jsonify({
                'error': 'Поисковый запрос должен содержать минимум 2 символа',
                'status': 'error'
            }), 400
        
        # Определение URL для поиска
        type_urls = {
            'gost': ['https://meganorm.ru/mega_doc/fire/standart/standart_0.html'],
            'federal-laws': ['https://meganorm.ru/mega_doc/fire/federalnyj-zakon/federalnyj-zakon_0.html'],
            'orders': ['https://meganorm.ru/mega_doc/fire/prikaz/prikaz_0.html'],
            'resolutions': ['https://meganorm.ru/mega_doc/fire/postanovlenie/postanovlenie_0.html']
        }
        
        if doc_type == 'all':
            search_urls = [url for urls in type_urls.values() for url in urls]
        else:
            search_urls = type_urls.get(doc_type, [])
        
        if not search_urls:
            return jsonify({
                'error': 'Неподдерживаемый тип документа',
                'available_types': list(type_urls.keys()) + ['all'],
                'status': 'error'
            }), 400
        
        all_documents = []
        for url in search_urls:
            try:
                documents = api.parse_document_list(url)
                all_documents.extend(documents)
            except Exception as e:
                print(f"Ошибка при парсинге {url}: {str(e)}")
                continue
        
        # Фильтрация по поисковому запросу
        query_lower = query.lower()
        filtered_docs = []
        
        for doc in all_documents:
            title_lower = doc['title'].lower()
            if query_lower in title_lower:
                # Добавляем релевантность
                doc['relevance'] = title_lower.count(query_lower)
                filtered_docs.append(doc)
        
        # Сортировка по релевантности
        filtered_docs.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        
        # Ограничиваем результаты
        max_results = min(100, len(filtered_docs))
        
        return jsonify({
            'documents': filtered_docs[:max_results],
            'query': query,
            'total': len(filtered_docs),
            'showing': max_results,
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@app.route('/api/types')
def get_document_types():
    """Получение списка доступных типов документов"""
    return jsonify({
        'types': {
            'gost': 'ГОСТы и стандарты',
            'federal-laws': 'Федеральные законы',
            'orders': 'Приказы',
            'resolutions': 'Постановления'
        },
        'status': 'success'
    })

@app.route('/api/health')
def health_check():
    """Проверка работоспособности API"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'service': 'MegaNorm API',
        'version': '1.1'
    })

@app.route('/')
def index():
    """Главная страница с документацией"""
    return jsonify({
        'message': 'MegaNorm API',
        'version': '1.1',
        'endpoints': {
            '/api/health': 'Проверка работоспособности',
            '/api/types': 'Список типов документов',
            '/api/documents/<type>': 'Список документов по типу',
            '/api/document?url=<url>': 'Детали документа',
            '/api/search?q=<query>': 'Поиск документов'
        },
        'status': 'running'
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Эндпоинт не найден',
        'status': 'error'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Внутренняя ошибка сервера',
        'status': 'error'
    }), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
