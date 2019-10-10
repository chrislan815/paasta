#!/usr/bin/env python
# Copyright 2015-2019 Yelp Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Usage: ./cleanup_nodes.py [options]

Command line options:

- -v, --verbose: Verbose output
- -n, --dry-run: Only report what would have been deleted
"""
import argparse
import logging
import sys
from typing import List, Tuple, Union
from kubernetes.client import V1Node, V1DeleteOptions
from kubernetes.client.rest import ApiException
from paasta_tools.kubernetes_tools import KubeClient
from paasta_tools.kubernetes_tools import get_all_nodes
from paasta_tools.utils import load_system_paasta_config

log = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Removes stale kubernetes CRDs.")
    parser.add_argument(
        "-v", "--verbose", action="store_true", dest="verbose", default=False
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", dest="dry_run", default=False
    )
    args = parser.parse_args()
    return args


def nodes_for_cleanup(nodes: List[V1Node]) -> List[V1Node]:
    not_ready = [
        node for node in nodes if not is_node_ready(node)
    ]
    return not_ready

def terminate_nodes(client: KubeClient, nodes: List[V1Node]) -> Tuple[List[str], List[Tuple[str, Exception]]]:
    success = []
    errors = []
    for node in nodes:
        try:
            body = V1DeleteOptions()
            client.core.delete_node(node, body=body, propagation_policy='foreground')
        except ApiException as e:
            errors.append((node, e))
            continue
        success.append(node)
    return (success, errors)

def is_node_ready(node: V1Node) -> bool:
    for condition in node.status.conditions:
        if condition.type == 'Ready':
            if condition.status == 'Unknown':
                return False
            return condition.status
    log.error(f"no KubeletReady condition found for node {node.metadata.name}. Conditions {node.status.conditions}")
    return True

def main() -> None:
    args = parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    dry_run = args.dry_run

    kube_client = KubeClient()
    all_nodes = get_all_nodes(kube_client)
    log.debug(f"found nodes in cluster {[node.metadata.name for node in all_nodes]}")
    filtered_nodes = nodes_for_cleanup(all_nodes)
    log.debug(f"nodes to be deleted: {[node.metadata.name for node in filtered_nodes]}")

    if not dry_run:
        success, errors = terminate_nodes(kube_client, [node.metadata.name for node in filtered_nodes])
    else:
        success, errors = [], []
        log.info("dry run mode detected: not deleting nodes")
    
    for node_name in success:
        log.info(f"successfully deleted node {node_name}")

    for node_name, exception in errors:
        log.error(f"error deleting node: {node_name}: {exception}")

    if errors:
        sys.exit(1)
        


if __name__ == "__main__":
    main()