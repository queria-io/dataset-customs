"""税関 統計品目表データパイプライン。

1. customs: 輸入統計品目表と輸出統計品目表の最新の版を CSV にする
2. dbt: dbt ビルド
"""

import logging

from dbt.cli.main import dbtRunner

from pipelines.customs import download_customs

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("pipelines")


def dbt_build():
    dbt = dbtRunner()
    for command in (["deps"], ["build"], ["docs", "generate"]):
        result = dbt.invoke(command)
        if not result.success:
            raise SystemExit(f"dbt {' '.join(command)} failed")


def main():
    logger.info("1/2: customs (輸入・輸出統計品目表)")
    download_customs()

    logger.info("2/2: dbt build")
    dbt_build()


if __name__ == "__main__":
    main()
