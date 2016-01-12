# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import httplib2
from oslo_serialization import jsonutils
import uuid

from searchlight.tests import functional

TENANT1 = str(uuid.uuid4())
TENANT2 = str(uuid.uuid4())
TENANT3 = str(uuid.uuid4())

MATCH_ALL = {"query": {"match_all": {}}, "sort": [{"name": {"order": "asc"}}]}
EMPTY_RESPONSE = {"hits": {"hits": [], "total": 0, "max_score": 0.0},
                  "_shards": {"successful": 0, "failed": 0, "total": 0},
                  "took": 1,
                  "timed_out": False}


class TestSearchApi(functional.FunctionalTest):
    """Test case for API functionality that's not plugin-specific, although
    it can use plugins for the sake of making requests
    """
    def test_server_up(self):
        self.assertTrue(self.ping_server(self.api_port))

    def test_elasticsearch(self):
        """Index a document and check elasticsearch for it to check
        things are working.
        """
        doc_id = str(uuid.uuid4())
        doc = {
            "owner": TENANT1,
            "is_public": True,
            "id": doc_id,
            "name": "owned by tenant 1",
            "owner": TENANT1,
            "members": [TENANT1]
        }

        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    doc,
                    TENANT1)

        # Test the raw elasticsearch response
        es_url = "http://localhost:%s/%s/%s/%s" % (
            self.api_server.elasticsearch_port,
            self.images_plugin.get_index_name(),
            self.images_plugin.get_document_type(),
            doc_id)

        response, content = httplib2.Http().request(es_url)
        json_content = jsonutils.loads(content)
        self.assertEqual(doc, json_content["_source"])

    def test_empty_results(self):
        """Test an empty dataset gets empty results."""
        response, json_content = self._search_request(MATCH_ALL, TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([], self._get_hit_source(json_content))

    def test_nested_objects(self):
        """Test queries against documents with nested complex objects."""
        doc1 = {
            "owner": TENANT1,
            "is_public": True,
            "id": str(uuid.uuid4()),
            "name": "owned by tenant 1",
            "namespace": "some.value1",
            "members": [TENANT1],
            "properties": [
                {"property": "prop1",
                 "title": "hello"},
                {"property": "prop2",
                 "title": "bye"}
            ]
        }
        doc2 = {
            "owner": TENANT1,
            "is_public": True,
            "id": str(uuid.uuid4()),
            "namespace": "some.value2",
            "name": "owned by tenant 1",
            "members": [TENANT1],
            "properties": [
                {"property": "prop1",
                 "title": "something else"},
                {"property": "prop2",
                 "title": "hello"}
            ]
        }

        self._index(self.metadefs_plugin.get_index_name(),
                    self.metadefs_plugin.get_document_type(),
                    [doc1, doc2],
                    TENANT1)

        def get_nested(qs):
            return {
                "query": {
                    "nested": {
                        "path": "properties",
                        "query": {
                            "query_string": {"query": qs}
                        }
                    }
                },
                "sort": [{"namespace": {"order": "asc"}}]
            }

        # Expect this to match both documents
        querystring = "properties.property:prop1"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1, doc2], self._get_hit_source(json_content))

        # Expect this to match only doc1
        querystring = "properties.property:prop1 AND properties.title:hello"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1], self._get_hit_source(json_content))

        # Expect this not to match any documents, because it
        # doesn't properly match any nested objects
        querystring = "properties.property:prop1 AND properties.title:bye"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([], self._get_hit_source(json_content))

        # Expect a match with
        querystring = "properties.property:prop3 OR properties.title:bye"
        query = get_nested(querystring)
        response, json_content = self._search_request(query,
                                                      TENANT1,
                                                      role="admin")
        self.assertEqual([doc1], self._get_hit_source(json_content))

    def test_query_none(self):
        """Test search when query is not specified"""
        id_1 = str(uuid.uuid4())
        tenant1_doc = {
            "owner": TENANT1,
            "id": id_1,
            "visibility": "private",
            "name": "owned by tenant 1",
            "members": []
        }

        self._index(self.images_plugin.get_index_name(),
                    self.images_plugin.get_document_type(),
                    [tenant1_doc],
                    TENANT1)

        response, json_content = self._search_request({"all_projects": True},
                                                      TENANT1)
        self.assertEqual(200, response.status)
        self.assertEqual([tenant1_doc], self._get_hit_source(json_content))
