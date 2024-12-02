from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Spotify API 認証情報
CLIENT_ID = 'f48dda32a0544428a6808ffc4a03e5ec'
CLIENT_SECRET = '898a3fa1764d4471aa965cc8044ce02b'
REDIRECT_URI = 'https://a2-flask-recommendation-app-b.onrender.com/callback'

SCOPE = 'user-read-recently-played user-library-read user-top-read'

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                               client_secret=CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope=SCOPE))

app = Flask(__name__)
app.secret_key = os.urandom(24)

FEATURES = ['energy', 'danceability', 'acousticness', 'valence', 'instrumentalness', 'loudness', 'tempo', 'mode']

def create_spotify_oauth():
    return SpotifyOAuth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET, redirect_uri=REDIRECT_URI, scope=SCOPE)

# surveyで保存された数値を-5〜5の範囲にスケーリングする
def scale_survey_preferences(user_preferences):
    scaled_preferences = {}

    # パラメータ名のリスト（質問項目に対応するパラメータ名）
    features = ['tempo', 'danceability', 'acousticness', 'energy', 'loudness', 'instrumentalness', 'valence', 'mode']

    for feature in features:
        # それぞれのパラメータに対する1つ目と2つ目の質問の値を取得
        value_1 = int(user_preferences.get(f"{feature}_1", 0))  # デフォルト値0（選択されていなければ）
        value_2 = int(user_preferences.get(f"{feature}_2", 0))  # デフォルト値0（選択されていなければ）

        # 2つの質問の値を平均化
        average_value = (value_1 + value_2) / 2

        # 平均値を-5〜5の範囲にスケーリング
        scaled_value = ((average_value + 10) / 20) * 10 - 5  # -10〜10 の範囲を -5〜5 にスケーリング

        # 結果を保存
        scaled_preferences[feature] = scaled_value

    return scaled_preferences

# アンケートの送信後にスケーリングして保存
@app.route('/survey', methods=['GET', 'POST'])
def survey():
    if request.method == 'POST':
        user_preferences = {
            'tempo_1': int(request.form['tempo_1']),
            'tempo_2': int(request.form['tempo_2']),
            'danceability_1': int(request.form['danceability_1']),
            'danceability_2': int(request.form['danceability_2']),
            'acousticness_1': int(request.form['acousticness_1']),
            'acousticness_2': int(request.form['acousticness_2']),
            'energy_1': int(request.form['energy_1']),
            'energy_2': int(request.form['energy_2']),
            'loudness_1': int(request.form['loudness_1']),
            'loudness_2': int(request.form['loudness_2']),
            'instrumentalness_1': int(request.form['instrumentalness_1']),
            'instrumentalness_2': int(request.form['instrumentalness_2']),
            'valence_1': int(request.form['valence_1']),
            'valence_2': int(request.form['valence_2']),
            'mode_1': int(request.form['mode_1']),
            'mode_2': int(request.form['mode_2']),
        }

        # スケーリングされた値を保存
        scaled_user_preferences = scale_survey_preferences(user_preferences)
        session['user_preferences'] = scaled_user_preferences
        return redirect(url_for('index'))  # indexに遷移

    return render_template('survey.html')

# 全ジャンルのデータを結合する関数
def load_all_genre_data():
    genre_files = {
        'pop': 'scaled_spotify_pop_features.csv',
        'rock': 'scaled_spotify_rock_features.csv',
        'hip-hop': 'scaled_spotify_hip-hop_features.csv',
        'edm': 'scaled_spotify_edm_features.csv',
        'jazz': 'scaled_spotify_jazz_features.csv'
    }

    # 全ジャンルのデータを読み込んで結合
    all_data = []
    for genre, file_path in genre_files.items():
        try:
            data = pd.read_csv(file_path)
            data['genre'] = genre  # データにジャンル情報を追加
            all_data.append(data)
        except FileNotFoundError:
            print(f"警告: {file_path} が見つかりませんでした。")
        except Exception as e:
            print(f"エラーが発生しました: {e}")
    
    # すべてのデータフレームを縦に結合
    all_data_df = pd.concat(all_data, ignore_index=True)

    # 必要な列だけを抽出
    all_data_df = all_data_df[['track_name', 'artist_name', 'id', 'energy', 'danceability',
                               'acousticness', 'valence', 'instrumentalness', 'loudness', 
                               'tempo', 'mode', 'genre']]

    return all_data_df

# 推薦システム
def recommend_top_songs(user_preferences, all_genre_data):
    user_preferences_df = pd.DataFrame([user_preferences])
    genre_features = all_genre_data[FEATURES]
    cosine_sim = cosine_similarity(user_preferences_df[FEATURES], genre_features)
    sim_scores = cosine_sim[0]
    top_indices = sim_scores.argsort()[::-1]

    recommendations = []
    for idx in top_indices:
        track_id = all_genre_data.iloc[idx]['id']
        recommendation = all_genre_data[['track_name', 'artist_name', 'id']].iloc[idx]
        recommendation['track_url'] = f"https://open.spotify.com/track/{track_id}"
        recommendations.append(recommendation)
        if len(recommendations) >= 7:
            break

    return pd.DataFrame(recommendations)

# indexページ（アンケート後のページ）
@app.route('/index')
def index():
    return render_template('index.html')

# 推薦を表示するページ
@app.route('/recommend', methods=['GET'])
def recommend():
    if 'user_preferences' not in session:
        return redirect(url_for('survey'))  # アンケート結果がない場合、surveyにリダイレクト

    user_preferences = session['user_preferences']
    all_genre_data = load_all_genre_data()

    recommendations = recommend_top_songs(user_preferences, all_genre_data)

    if isinstance(recommendations, pd.DataFrame):
        return render_template('recommend.html', recommendations=recommendations.to_dict(orient='records'))

    return jsonify(recommendations)

# ログインページ（Spotify認証ページ）
@app.route('/login')
def login():
    sp_oauth = create_spotify_oauth()
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

# Spotify認証後のコールバック
@app.route('/callback')
def callback():
    sp_oauth = create_spotify_oauth()
    session.clear()
    code = request.args.get('code')
    if code:
        token_info = sp_oauth.get_access_token(code)
        session['token_info'] = token_info
        return redirect(url_for('survey'))  # Spotify認証後にsurveyページに遷移
    else:
        return jsonify({"error": "Spotify認証に失敗しました。"}), 400

# ルート（/）にアクセスされた場合、ログイン状態を確認して適切なページにリダイレクト
@app.route('/')
def home():
    # ユーザーがSpotifyにログインしていない場合、/loginにリダイレクト
    if 'token_info' not in session:
        return redirect(url_for('login'))  # Spotify認証ページにリダイレクト

    # ユーザーがアンケートをまだ送信していない場合、/surveyにリダイレクト
    if 'user_preferences' not in session:
        return redirect(url_for('survey'))  # アンケートページにリダイレクト

    # それ以外の場合、indexにリダイレクト
    return redirect(url_for('index'))

# ログアウト処理
@app.route('/logout')
def logout():
    session.clear()  # セッションをクリアしてログアウト
    return redirect(url_for('login'))  # ログインページにリダイレクト


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8888))  # PORT環境変数がない場合はデフォルトで5000を使用
    app.run(debug=True, host='0.0.0.0', port=port)