"""Handmade TMDB and OMDb payloads shaped like the real API responses."""

MOVIE_DETAILS = {
    "id": 354912,
    "title": "Coco",
    "original_title": "Coco",
    "release_date": "2017-10-27",
    "runtime": 105,
    "overview": "Aspiring musician Miguel enters the Land of the Dead.",
    "original_language": "en",
    "popularity": 91.2,
    "vote_average": 8.2,
    "vote_count": 20000,
    "poster_path": "/poster-coco.jpg",
    "backdrop_path": "/backdrop-coco.jpg",
    "imdb_id": "tt2380307",
    "genres": [{"id": 16, "name": "Animation"}, {"id": 10751, "name": "Family"}],
    "keywords": {"keywords": [{"id": 1, "name": "afterlife"}, {"id": 2, "name": "music"}]},
    "external_ids": {"imdb_id": "tt2380307"},
    "credits": {
        "cast": [
            {"name": "Anthony Gonzalez", "character": "Miguel", "profile_path": "/p1.jpg"},
            {"name": "Gael Garcia Bernal", "character": "Hector", "profile_path": "/p2.jpg"},
        ]
    },
    "videos": {
        "results": [
            {"site": "YouTube", "type": "Trailer", "key": "xlnPHQ3TLX8", "official": True},
            {"site": "YouTube", "type": "Clip", "key": "clip123", "official": True},
        ]
    },
    "watch/providers": {
        "results": {
            "EG": {
                "link": "https://www.themoviedb.org/movie/354912/watch?locale=EG",
                "flatrate": [
                    {"provider_id": 337, "provider_name": "Disney Plus", "logo_path": "/dp.jpg"}
                ],
            },
            "MA": {
                "link": "https://www.themoviedb.org/movie/354912/watch?locale=MA",
                "flatrate": [
                    {"provider_id": 337, "provider_name": "Disney Plus", "logo_path": "/dp.jpg"}
                ],
                "rent": [{"provider_id": 2, "provider_name": "Apple TV", "logo_path": "/atv.jpg"}],
            },
        }
    },
}

TV_DETAILS = {
    "id": 456,
    "name": "Example Show",
    "original_name": "Example Show",
    "first_air_date": "2020-01-15",
    "episode_run_time": [45],
    "overview": "A show used in tests.",
    "original_language": "en",
    "popularity": 55.0,
    "vote_average": 7.7,
    "vote_count": 900,
    "poster_path": "/poster-show.jpg",
    "backdrop_path": None,
    "genres": [{"id": 18, "name": "Drama"}],
    "keywords": {"results": [{"id": 3, "name": "small town"}]},
    "external_ids": {"imdb_id": "tt7654321"},
    "credits": {"cast": []},
    "videos": {"results": []},
    "watch/providers": {"results": {}},
}

TRENDING_MOVIES = {
    "page": 1,
    "total_pages": 1,
    "results": [
        {
            "id": 354912,
            "media_type": "movie",
            "title": "Coco",
            "poster_path": "/poster-coco.jpg",
            "backdrop_path": "/backdrop-coco.jpg",
            "release_date": "2017-10-27",
            "vote_average": 8.2,
        },
        {
            "id": 999999,
            "media_type": "movie",
            "title": "No Poster Film",
            "poster_path": None,
            "release_date": "2024-01-01",
            "vote_average": 5.0,
        },
    ],
}

SEARCH_MULTI = {
    "page": 1,
    "total_pages": 1,
    "results": [
        {
            "id": 354912,
            "media_type": "movie",
            "title": "Coco",
            "poster_path": "/poster-coco.jpg",
            "release_date": "2017-10-27",
            "vote_average": 8.2,
        },
        {"id": 111, "media_type": "person", "name": "Someone"},
        {
            "id": 456,
            "media_type": "tv",
            "name": "Example Show",
            "poster_path": "/poster-show.jpg",
            "first_air_date": "2020-01-15",
            "vote_average": 7.7,
        },
    ],
}

MOVIE2_DETAILS = {
    "id": 550,
    "title": "Another Film",
    "original_title": "Another Film",
    "release_date": "2019-05-01",
    "runtime": 99,
    "overview": "A third title nobody has watched yet.",
    "original_language": "en",
    "popularity": 40.0,
    "vote_average": 7.1,
    "vote_count": 5000,
    "poster_path": "/poster-another.jpg",
    "backdrop_path": None,
    "imdb_id": None,
    "genres": [{"id": 18, "name": "Drama"}],
    "keywords": {"keywords": []},
    "external_ids": {},
    "credits": {"cast": []},
    "videos": {"results": []},
    "watch/providers": {"results": {}},
}

ON_THE_AIR = {
    "page": 1,
    "total_pages": 1,
    "results": [
        {
            "id": 456,
            "name": "Example Show",
            "poster_path": "/poster-show.jpg",
            "first_air_date": "2020-01-15",
            "vote_average": 7.7,
        }
    ],
}

PROVIDER_LIST = {
    "results": [
        {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/nf.jpg"},
        {"provider_id": 337, "provider_name": "Disney Plus", "logo_path": "/dp.jpg"},
    ]
}

OMDB_RESPONSE = {
    "Response": "True",
    "imdbRating": "8.4",
    "Metascore": "81",
    "Ratings": [
        {"Source": "Internet Movie Database", "Value": "8.4/10"},
        {"Source": "Rotten Tomatoes", "Value": "97%"},
        {"Source": "Metacritic", "Value": "81/100"},
    ],
}
