{# pipelines/customs.py が最新の版から data/customs/import_item.csv に書き出したものを、そのまま読む。 #}

select * from read_csv('data/customs/import_item.csv', header = true, all_varchar = true)
