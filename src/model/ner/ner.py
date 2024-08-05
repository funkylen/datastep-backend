import httpx

from infra.env import NER_SERVICE_URL


class HTTP_NER:
    def __init__(self, url: str = NER_SERVICE_URL, k: int = 100, timeout: int = 100):
        self.__client = httpx.Client()
        self.__k = k
        self.__timeout = timeout
        self.__url = url

    def predict(self, nomenclatures: list[str]) -> list[str]:
        noms_brands_list = []

        nomenclatures_count = len(nomenclatures)
        noms_chunk_size = nomenclatures_count // self.__k + 1
        for i in range(0, nomenclatures_count, noms_chunk_size):
            noms_chunk = nomenclatures[i:noms_chunk_size]

            if len(noms_chunk) == 0:
                break

            try:
                body = {
                    "nomenclatures": noms_chunk,
                }
                response = self.__client.post(
                    self.__url,
                    json=body,
                    timeout=self.__timeout,
                )
                response_json = response.json()
                response_brands = response_json['brands']
                noms_brands_list.extend(response_brands)

            except Exception as e:
                print(f"Index chunk {i} - {e}")

        return noms_brands_list

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__client.close()


ner_service = HTTP_NER()
