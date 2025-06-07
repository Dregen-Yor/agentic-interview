from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
import pymongo
import json
import jwt
from datetime import datetime, timedelta, timezone
from bson.objectid import ObjectId

# --- HELPER FUNCTION TO GET DB ---
def get_db():
    """Helper function to connect to MongoDB and get the database."""
    client = pymongo.MongoClient(settings.MONGO_URI)
    db = client[settings.MONGO_DATABASE_NAME]
    return db, client

# --- REPLACEMENT for create_user ---
@csrf_exempt
def new_user(request):
    """Creates a new user with a hashed password and an empty resume."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get('name')
        password = data.get('password')

        if not all([name, password]):
            return JsonResponse({'error': 'Name and password are required'}, status=400)

        # Hash the password for security
        hashed_password = make_password(password)

        db, client = get_db()
        users_collection = db['users']
        
        # Check if user already exists
        if users_collection.find_one({'name': name}):
            client.close()
            return JsonResponse({'error': 'User with this name already exists'}, status=409)

        user_id = users_collection.insert_one({
            'name': name,
            'password': hashed_password,
        }).inserted_id
        
        # Create an empty resume for the new user
        resumes_collection = db['resumes']
        resumes_collection.insert_one({
            '_id': user_id,
            'content': {}
        })

        client.close()
        return JsonResponse({'message': 'User created successfully', 'user_id': str(user_id)}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'An unexpected error occurred', 'details': str(e)}, status=500)


# --- NEW function check_user ---
@csrf_exempt
def check_user(request):
    """Checks user credentials and returns a JWT token if valid."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get('name')
        password = data.get('password')

        if not name or not password:
            return JsonResponse({'error': 'Name and password are required'}, status=400)

        db, client = get_db()
        users_collection = db['users']
        user = users_collection.find_one({'name': name})
        client.close()

        if user and check_password(password, user['password']):
            # Password is correct, generate JWT
            payload = {
                'user_id': str(user['_id']),
                'name': user['name'],
                'exp': datetime.now(timezone.utc) + timedelta(hours=1)  # Token expires in 1 hour
            }
            token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
            
            return JsonResponse({'message': 'Login successful', 'token': token})
        else:
            return JsonResponse({'error': 'Invalid credentials'}, status=401)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'An unexpected error occurred', 'details': str(e)}, status=500)

@csrf_exempt
def verify_token(request):
    """Verifies a JWT token from the Authorization header."""
    if request.method != 'POST':
        # 通常验证请求使用 POST 或 GET，这里为保持一致性使用 POST
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        # 从请求头中获取 token
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Authorization header missing or invalid'}, status=401)
        
        token = auth_header.split(' ')[1]

        # 解码并验证 token
        # jwt.decode 会自动检查是否过期，如果过期会抛出 ExpiredSignatureError
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])

        # 如果需要，可以进一步验证 payload 中的用户是否存在于数据库
        
        return JsonResponse({'message': 'Token is valid', 'user_id': payload['user_id']}, status=200)

    except jwt.ExpiredSignatureError:
        return JsonResponse({'error': 'Token has expired'}, status=401)
    except jwt.InvalidTokenError:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    except Exception as e:
        return JsonResponse({'error': 'An unexpected error occurred', 'details': str(e)}, status=500)

@csrf_exempt
def get_user_resume(request):
    """Gets a user's resume, requires JWT authentication."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Only GET method is allowed'}, status=405)
    
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Authorization header missing or invalid'}, status=401)
        
        token = auth_header.split(' ')[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        user_id = ObjectId(payload['user_id'])

        db, client = get_db()
        resumes_collection = db['resumes']
        resume = resumes_collection.find_one({'_id': user_id})
        client.close()

        if resume:
            return JsonResponse({'resume': resume.get('content', {})}, status=200)
        else:
            return JsonResponse({'error': 'Resume not found'}, status=404)

    except jwt.ExpiredSignatureError:
        return JsonResponse({'error': 'Token has expired'}, status=401)
    except jwt.InvalidTokenError:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    except Exception as e:
        return JsonResponse({'error': 'An unexpected error occurred', 'details': str(e)}, status=500)


@csrf_exempt
def update_user_resume(request):
    """Updates a user's resume, requires JWT authentication."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)

    try:
        # Token validation
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Authorization header missing or invalid'}, status=401)
        
        token = auth_header.split(' ')[1]
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        user_id = ObjectId(payload['user_id'])

        # Get resume content from request body
        request_data = json.loads(request.body)
        new_content = request_data.get('content')

        if new_content is None:
            return JsonResponse({'error': 'Missing "content" in request body'}, status=400)

        # Update database
        db, client = get_db()
        resumes_collection = db['resumes']
        result = resumes_collection.update_one(
            {'_id': user_id},
            {'$set': {'content': new_content}}
        )
        client.close()

        if result.matched_count == 0:
            return JsonResponse({'error': 'Resume not found for the user'}, status=404)
        
        return JsonResponse({'message': 'Resume updated successfully'}, status=200)

    except jwt.ExpiredSignatureError:
        return JsonResponse({'error': 'Token has expired'}, status=401)
    except jwt.InvalidTokenError:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'An unexpected error occurred', 'details': str(e)}, status=500)
    